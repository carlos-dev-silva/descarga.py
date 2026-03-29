import streamlit as st
import pandas as pd
from datetime import date
import re
import io

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# 1. Função de Formatação de Moeda
def formatar_moeda(valor):
    try:
        val = float(valor)
        if val == 0: return "R$ 0,00"
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

# 2. Limpeza Numérica
def limpar_para_numero(valor):
    if pd.isna(valor): return 0.0
    s = str(valor).strip().replace('R$', '').replace(' ', '')
    if not s or s.lower() == 'nan': return 0.0
    try:
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except:
        return 0.0

# 3. Função para Gerar Excel (Exportação)
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Resumo_Pedidos')
    return output.getvalue()

@st.cache_data
def load_data():
    try:
        df_f = pd.read_csv("Faturamento.csv", sep=";", encoding='latin-1', dtype=str) 
        df_v = pd.read_csv("Vendedores.csv", sep=";", encoding='latin-1', dtype=str)
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        df_f['VALOR_NUM'] = df_f.iloc[:, 22].apply(limpar_para_numero)
        df_f['PESO_NUM'] = df_f.iloc[:, 26].apply(limpar_para_numero)

        def remover_fabricante(row):
            prod, fab = str(row.iloc[15]).strip(), str(row.iloc[7]).strip()
            if fab.lower() in prod.lower():
                return re.sub(re.escape(fab), '', prod, flags=re.IGNORECASE).replace(' - ', ' ').strip()
            return prod
        df_f.iloc[:, 15] = df_f.apply(remover_fabricante, axis=1)
        
        return df_f.dropna(subset=['DATA_FILTRO']), df_v
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return None, None

df_fat, df_vend = load_data()

if df_fat is not None:
    # --- BARRA LATERAL ---
    with st.sidebar:
        st.header("📌 Filtros")
        data_sel = st.date_input("Data da Descarga", value=date(2026, 3, 10), format="DD/MM/YYYY")
        vendedores = sorted(df_vend.iloc[:, 1].dropna().unique().tolist())
        nome_vend = st.selectbox("Selecione o Vendedor", vendedores)
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()

    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           ((df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
            (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend))
    
    df_filtrado = df_fat[mask].copy()
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    st.subheader("📋 Resumo dos Pedidos do Dia")
    
    if df_filtrado.empty:
        st.warning("Nenhum dado para este filtro.")
    else:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', # COD_CLI
            df_filtrado.columns[5]: 'first', # CLIENTE
            'VALOR_NUM': 'sum', 
            df_filtrado.columns[11]: 'first', # NFE
            df_filtrado.columns[8]: 'first'   # HORA
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        # KPIs e Botão de Exportar
        c1, c2, c3 = st.columns([1, 1, 1])
        c1.metric("TOTAL VENDAS", formatar_moeda(df_resumo['VALOR'].sum()))
        p_total = df_filtrado['PESO_NUM'].sum()
        c2.metric("PESO TOTAL", f"{p_total:,.3f} kg".replace(",", "X").replace(".", ",").replace("X", "."))
        
        # Gerar o arquivo Excel para Download
        excel_data = to_excel(df_resumo)
        c3.download_button(
            label="📥 Exportar Resumo (Excel)",
            data=excel_data,
            file_name=f'Resumo_{nome_vend}_{data_sel}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        df_display = df_resumo.copy()
        df_display['VALOR'] = df_display['VALOR'].apply(formatar_moeda)
        
        selecao = st.dataframe(
            df_display, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row",
            column_config={
                "CLIENTE": st.column_config.TextColumn(width="large"),
                "VALOR": st.column_config.TextColumn(width="medium")
            }
        )

        st.divider() 

        # --- DETALHE DO PEDIDO ---
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_pedido = df_resumo.iloc[idx]['PEDIDO'] 
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_pedido]
            
            st.subheader(f"🔍 Detalhe do Pedido: {num_pedido}")
            
            # Tabela de Detalhes
            df_det = pd.DataFrame({
                'CÓDIGO': df_itens.iloc[:, 13],
                'PRODUTO': df_itens.iloc[:, 15],
                'FABRICANTE': df_itens.iloc[:, 7],
                'CX': df_itens.iloc[:, 19].astype(str),
                'UN': df_itens.iloc[:, 20].astype(str),
                'VALOR': df_itens['VALOR_NUM'].apply(formatar_moeda),
                'PESO': df_itens['PESO_NUM'].apply(lambda x: f"{x:,.3f} kg".replace(".", ","))
            })
            
            st.dataframe(
                df_det, hide_index=True, use_container_width=True,
                column_config={"PRODUTO": st.column_config.TextColumn(width="large")}
            )
            
            # Botão Extra: Exportar apenas este pedido selecionado
            excel_pedido = to_excel(df_det)
            st.download_button(
                label=f"📥 Baixar Itens do Pedido {num_pedido}",
                data=excel_pedido,
                file_name=f'Pedido_{num_pedido}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
