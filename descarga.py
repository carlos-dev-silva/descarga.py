import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# Função para formatar moeda no padrão Brasileiro
def formatar_moeda(valor):
    try:
        texto = f"{valor:,.2f}"
        texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"
    except:
        return "R$ 0,00"

# Lendo os dados dos CSVs (conforme estão no seu GitHub)
@st.cache_data
def load_data():
    try:
        # Usamos sep=";" porque o Excel em português salva assim por padrão
        df_f = pd.read_csv("Faturamento.csv", sep=";") 
        df_v = pd.read_csv("Vendedores.csv", sep=";")
        
        # Ajuste da data
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        df_f = df_f.dropna(subset=['DATA_FILTRO'])
        
        return df_f, df_v
    except Exception as e:
        st.error(f"Erro ao ler os arquivos: {e}")
        return None, None

df_fat, df_vend = load_data()

if df_fat is not None:
    # --- BARRA LATERAL ---
    with st.sidebar:
        st.header("📌 Filtros")
        data_sel = st.date_input("Data da Descarga", value=date(2026, 3, 26), format="DD/MM/YYYY")
        
        vendedores_lista = df_vend.iloc[:, 1].dropna().unique().tolist()
        vendedores_ordenados = sorted(vendedores_lista)
        
        nome_vend = st.selectbox("Selecione o Vendedor", vendedores_ordenados)
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()
        nome_vend_limpo = str(nome_vend).strip()

    # --- FILTRAGEM ---
    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           (
               (df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
               (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend_limpo)
           )
    df_filtrado = df_fat[mask].copy()
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    # --- EXIBIÇÃO ---
    st.subheader("📋 Resumo dos Pedidos")
    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para este filtro.")
    else:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[5]: 'first', 
            df_filtrado.columns[22]: 'sum',
            df_filtrado.columns[8]: 'first'  
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'CLIENTE', 'VALOR', 'HORA']
        
        st.metric("TOTAL VENDAS", formatar_moeda(df_resumo['VALOR'].sum()))
        st.dataframe(df_resumo, use_container_width=True, hide_index=True)
