import streamlit as st
import pandas as pd
from datetime import date
import re

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# 1. Formatação de Moeda Brasileira (Ex: R$ 1.500,50)
def formatar_moeda(valor):
    try:
        val = float(valor)
        if val == 0: return "R$ 0,00"
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

# 2. Limpeza Numérica (Garante que Peso e Valor não fiquem em 0)
def limpar_para_numero(valor):
    if pd.isna(valor): return 0.0
    s = str(valor).strip().replace('R$', '').replace(' ', '')
    if not s or s.lower() == 'nan': return 0.0
    try:
        # Trata 1.234,56 ou 1234,56
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except:
        return 0.0

# 3. SOLUÇÃO DEFINITIVA PARA O EAN (Mata o 7,90E+12)
def limpar_ean(valor):
    if pd.isna(valor) or str(valor).strip() == "" or str(valor).lower() == "nan": 
        return ""
    try:
        # Converte o "7.9E+12" para 7900000000000 e remove o .0 do final
        s = str(valor).strip()
        # Se contiver 'E', forçamos a conversão via float para "esticar" o número
        if 'E' in s.upper() or '.' in s:
            return f"{float(s):.0f}"
        return s
    except:
        return str(valor).split('.')[0].strip()

@st.cache_data
def load_data():
    try:
        # Lê como string para evitar que o Pandas estrague os números no início
        df_f = pd.read_csv("Faturamento.csv", sep=";", encoding='latin-1', dtype=str) 
        df_v = pd.read_csv("Vendedores.csv", sep=";", encoding='latin-1', dtype=str)
        
        # Limpeza de Data (Coluna 9)
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        
        # Limpeza de Valores e Pesos
        df_f['VALOR_NUM'] = df_f.iloc[:, 22].apply(limpar_para_numero)
        df_f['PESO_NUM'] = df_f.iloc[:, 26].apply(limpar_para_numero)
        
        # --- APLICAÇÃO DA LIMPEZA DO EAN ---
        df_f.iloc[:, 14] = df_f.iloc[:, 14].apply(limpar_ean)
        
        # --- LIMPEZA DA DESCRIÇÃO (Retira o Fabricante) ---
        def remover_fabricante(row):
            prod = str(row.iloc[15]).strip()
            fab = str(row.iloc[7]).strip()
            if fab != "nan" and fab.lower() in prod.lower():
                regex = re.compile(re.escape(fab), re.IGNORECASE)
                res = regex.sub('', prod)
                return res.replace(' - ', ' ').strip()
            return prod

        df_f.iloc[:, 15] = df_f.apply(remover_fabricante, axis=1)
        
        return df_f.dropna(subset=['DATA_FILTRO']), df_v
    except Exception as e:
        st.error(f"Erro nos dados: {e}")
        return None, None

df_fat, df_vend = load_data()

if df_fat is not None:
    with st.sidebar:
        st.header("📌 Filtros")
        data_sel = st.date_input("Data da Descarga", value=date(2026, 3, 26), format="DD/MM/YYYY")
        vendedores = sorted(df_vend.iloc[:, 1].dropna().unique().tolist())
        nome_vend = st.selectbox("Selecione o Vendedor", vendedores)
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()

    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           ((df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
            (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend))
    
    df_filtrado = df_fat[mask].copy()
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    # --- RESUMO ---
    st.subheader("📋 Resumo dos Pedidos do Dia")
    
    if df_filtrado.empty:
        st.warning("Sem pedidos para esta seleção.")
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
        p_total = df_filtrado['PESO_NUM'].sum()
        c2.metric("PESO TOTAL", f"{p_total:,.3f} kg".replace(",", "X").replace(".", ",").replace("X", "."))

        df_display = df_resumo.copy()
        df_display['VALOR'] = df_display['VALOR'].apply(formatar_moeda)
        
        # CLIENTE Aumentado e outros Reduzidos
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
                "CLIENTE": st.column_config.TextColumn(width=600), # LARGO
                "VALOR": st.column_config.TextColumn(width="medium"),
                "NFE": st.column_config.TextColumn(width="small")
            }
        )

        st.divider() 

        # --- DETALHE ---
        st.subheader("🔍 Detalhe do Pedido")
        
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_pedido = df_resumo.iloc[idx]['PEDIDO'] 
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_pedido]
            
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.info(f"**Cliente:** {df_itens.iloc[0, 5]}\n\n**Pedido:** {num_pedido}")
            with col_info2:
                st.warning(f"**Coligação:** {df_itens.iloc[0, 6] if pd.notna(df_itens.iloc[0, 6]) else 'SEM'}\n\n**NF-e:** {df_itens.iloc[0, 11]}")
            with col_info3:
                st.success(f"**Valor:** {formatar_moeda(df_itens['VALOR_NUM'].sum())}\n\n**Peso:** {df_itens['PESO_NUM'].sum():,.3f} kg".replace(".", ","))

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
                    "PRODUTO": st.column_config.TextColumn(width=500), # LARGO
                    "FABRICANTE": st.column_config.TextColumn(width="medium"),
                    "EAN": st.column_config.TextColumn(width="medium")
                }
            )
