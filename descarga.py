import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# 1. Função para formatar moeda
def formatar_moeda(valor):
    try:
        if pd.isna(valor) or valor == 0: return "R$ 0,00"
        texto = f"{valor:,.2f}"
        texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"
    except:
        return "R$ 0,00"

# 2. Função para limpar valores numéricos
def limpar_valor(valor):
    if pd.isna(valor): return 0.0
    s = str(valor).strip().replace('R$', '').replace(' ', '')
    if not s: return 0.0
    try:
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except:
        return 0.0

# 3. Função para corrigir EAN e evitar notação científica
def corrigir_ean(valor):
    if pd.isna(valor) or str(valor).strip() == "" or str(valor).lower() == "nan":
        return ""
    try:
        return f"{float(valor):.0f}"
    except:
        return str(valor).strip()

@st.cache_data
def load_data():
    try:
        df_f = pd.read_csv("Faturamento.csv", sep=";", encoding='latin-1', dtype=str) 
        df_v = pd.read_csv("Vendedores.csv", sep=";", encoding='latin-1', dtype=str)
        
        # Ajuste de Datas, Valores e EAN
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        df_f['VALOR_NUM'] = df_f.iloc[:, 22].apply(limpar_valor)
        df_f['PESO_NUM'] = df_f.iloc[:, 26].apply(limpar_valor)
        df_f.iloc[:, 14] = df_f.iloc[:, 14].apply(corrigir_ean)
        
        # --- LÓGICA PARA RETIRAR REDUNDÂNCIA DO PRODUTO ---
        # Remove o nome do fabricante (Col 7) de dentro da descrição do produto (Col 15)
        def limpar_descricao(row):
            prod = str(row.iloc[15])
            fab = str(row.iloc[7])
            if fab in prod:
                return prod.replace(fab, "").strip(" -")
            return prod

        df_f.iloc[:, 15] = df_f.apply(limpar_descricao, axis=1)
        
        df_f = df_f.dropna(subset=['DATA_FILTRO'])
        return df_f, df_v
    except Exception as e:
        st.error(f"Erro ao ler os arquivos: {e}")
        return None, None

df_fat, df_vend = load_data()

if df_fat is not None:
    with st.sidebar:
        st.header("📌 Filtros")
        data_sel = st.date_input("Data da Descarga", value=date(2026, 3, 26), format="DD/MM/YYYY")
        vendedores_lista = sorted(df_vend.iloc[:, 1].dropna().unique().tolist())
        nome_vend = st.selectbox("Selecione o Vendedor", vendedores_lista)
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()
        nome_vend_limpo = str(nome_vend).strip()

    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           ((df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
            (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend_limpo))
    
    df_filtrado = df_fat[mask].copy()
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    # --- RESUMO DOS PEDIDOS ---
    st.subheader("📋 Resumo dos Pedidos do Dia")
    
    if df_filtrado.empty:
        st.warning("Nenhum pedido encontrado.")
    else:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', # COD_CLI
            df_filtrado.columns[5]: 'first', # CLIENTE
            'VALOR_NUM': 'sum', 
            df_filtrado.columns[11]: 'first', # NFE
            df_filtrado.columns[8]: 'first'   # HORA
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        c1, c2 = st.columns(2)
        c1.metric("TOTAL VENDAS", formatar_moeda(df_resumo['VALOR'].sum()))
        c2.metric("PESO TOTAL", f"{df_filtrado['PESO_NUM'].sum():,.3f} kg".replace(",", "X").replace(".", ",").replace("X", "."))

        # Formatação Visual da Tabela de Resumo
        df_display = df_resumo.copy()
        df_display['VALOR'] = df_display['VALOR'].apply(formatar_moeda)
        
        # AJUSTE DE LARGURA: Pedido, Hora e Cod_Cli reduzidos; Cliente aumentado
        selecao = st.dataframe(
            df_display, 
            use_container_width=True, 
            hide_index=True, 
            on_select="rerun", 
            selection_mode="single-row",
            column_config={
                "PEDIDO": st.column_config.TextColumn(width="small"),
                "HORA": st.column_config.TextColumn(width="small"),
                "COD_CLI": st.column_config.TextColumn(width="small"),
                "CLIENTE": st.column_config.TextColumn(width="large"),
                "VALOR": st.column_config.TextColumn(width="medium"),
                "NFE": st.column_config.TextColumn(width="small")
            }
        )

        st.divider() 

        # --- DETALHE DO PEDIDO ---
        st.subheader("🔍 Detalhe do Pedido Selecionado")
        
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_pedido = df_resumo.iloc[idx]['PEDIDO'] 
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_pedido]
            
            coligacao = df_itens.iloc[0, 6]
            colig_txt = coligacao if pd.notna(coligacao) and str(coligacao).strip() != "" else "NÃO TEM COLIGAÇÃO"

            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.info(f"**Cliente:** {df_itens.iloc[0, 5]}\n\n**Pedido:** {num_pedido}")
            with col_info2:
                st.warning(f"**Coligação:** {colig_txt}\n\n**NF-e:** {df_itens.iloc[0, 11]}")
            with col_info3:
                st.success(f"**Valor Pedido:** {formatar_moeda(df_itens['VALOR_NUM'].sum())}")

            # Ajuste de Largura no Detalhe: Código reduzido, Produto aumentado
            df_det = pd.DataFrame({
                'CÓDIGO': df_itens.iloc[:, 13],
                'PRODUTO': df_itens.iloc[:, 15],
                'FABRICANTE': df_itens.iloc[:, 7],
                'CX': df_itens.iloc[:, 19],
                'UN': df_itens.iloc[:, 20],
                'VALOR': df_itens['VALOR_NUM'].apply(formatar_moeda),
                'PESO': df_itens['PESO_NUM'].apply(lambda x: f"{x:,.3f} kg".replace(".", ",")),
                'EAN': df_itens.iloc[:, 14]
            })
            
            st.dataframe(
                df_det, 
                hide_index=True, 
                use_container_width=True,
                column_config={
                    "CÓDIGO": st.column_config.TextColumn(width="small"),
                    "PRODUTO": st.column_config.TextColumn(width="large"),
                    "FABRICANTE": st.column_config.TextColumn(width="medium"),
                    "EAN": st.column_config.TextColumn(width="medium")
                }
            )
