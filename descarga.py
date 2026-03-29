import streamlit as st
import pandas as pd
from datetime import date
import re

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# 1. Formatação de Moeda (Padrão R$ 1.234,56)
def formatar_moeda(valor):
    try:
        val = float(valor)
        if val == 0: return "R$ 0,00"
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

# 2. Limpeza de Valores (Resolve o R$ 0,00)
def limpar_para_numero(valor):
    if pd.isna(valor): return 0.0
    s = str(valor).strip().replace('R$', '').replace(' ', '')
    try:
        # Se tem ponto e vírgula (1.234,56)
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        # Se tem apenas vírgula (1234,56)
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except:
        return 0.0

# 3. Limpeza do EAN (Tenta recuperar os dígitos sem zerar)
def limpar_ean(valor):
    if pd.isna(valor) or str(valor).strip() == "" or str(valor).lower() == "nan": 
        return ""
    s = str(valor).strip()
    try:
        # Se o CSV trouxe notação científica, tentamos converter para float e depois int
        # Mas atenção: se o CSV já tiver salvado como 7.9E+12, a precisão foi perdida no Excel
        if 'E' in s.upper() or '.' in s:
            return str(int(float(s)))
        return s.split('.')[0] # Remove o .0 se existir
    except:
        return s

@st.cache_data
def load_data():
    try:
        # Lendo como string para o Pandas não tentar "ajudar" e estragar o EAN
        df_f = pd.read_csv("Faturamento.csv", sep=";", encoding='latin-1', dtype=str) 
        df_v = pd.read_csv("Vendedores.csv", sep=";", encoding='latin-1', dtype=str)
        
        # Limpeza básica
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        df_f['VALOR_NUM'] = df_f.iloc[:, 22].apply(limpar_para_numero)
        df_f['PESO_NUM'] = df_f.iloc[:, 26].apply(limpar_para_numero)
        
        # Correção do EAN
        df_f.iloc[:, 14] = df_f.iloc[:, 14].apply(limpar_ean)
        
        # Retira fabricante do nome do produto
        def remover_fab(row):
            prod, fab = str(row.iloc[15]), str(row.iloc[7])
            if fab.lower() in prod.lower():
                return re.sub(re.escape(fab), '', prod, flags=re.IGNORECASE).replace(' - ', ' ').strip()
            return prod
        df_f.iloc[:, 15] = df_f.apply(remover_fab, axis=1)
        
        return df_f.dropna(subset=['DATA_FILTRO']), df_v
    except Exception as e:
        st.error(f"Erro nos dados: {e}")
        return None, None

df_fat, df_vend = load_data()

if df_fat is not None:
    with st.sidebar:
        st.header("📌 Filtros")
        data_sel = st.date_input("Data", value=date(2026, 3, 10), format="DD/MM/YYYY")
        vendedores = sorted(df_vend.iloc[:, 1].dropna().unique().tolist())
        nome_vend = st.selectbox("Vendedor", vendedores)
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()

    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           ((df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
            (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend))
    
    df_filtrado = df_fat[mask].copy()
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    if df_filtrado.empty:
        st.warning("Sem dados.")
    else:
        # KPIs
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', df_filtrado.columns[5]: 'first',
            'VALOR_NUM': 'sum', df_filtrado.columns[11]: 'first', df_filtrado.columns[8]: 'first'
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        c1, c2 = st.columns(2)
        c1.metric("TOTAL VENDAS", formatar_moeda(df_resumo['VALOR'].sum()))
        c2.metric("PESO TOTAL", f"{df_filtrado['PESO_NUM'].sum():,.3f} kg".replace(",", "X").replace(".", ",").replace("X", "."))

        # TABELA PRINCIPAL (CLIENTE MUITO LARGO)
        df_disp = df_resumo.copy()
        df_disp['VALOR'] = df_disp['VALOR'].apply(formatar_moeda)
        
        selecao = st.dataframe(
            df_disp, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row",
            column_config={
                "CLIENTE": st.column_config.TextColumn(width=800), # MÁXIMO POSSÍVEL
                "PEDIDO": st.column_config.TextColumn(width="small"),
                "HORA": st.column_config.TextColumn(width="small")
            }
        )

        st.divider()

        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_ped = df_resumo.iloc[idx]['PEDIDO']
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_ped]
            
            # Detalhes
            df_det = pd.DataFrame({
                'CÓDIGO': df_itens.iloc[:, 13],
                'PRODUTO': df_itens.iloc[:, 15],
                'FABRICANTE': df_itens.iloc[:, 7],
                'VALOR': df_itens['VALOR_NUM'].apply(formatar_moeda),
                'EAN': df_itens.iloc[:, 14]
            })
            st.dataframe(df_det, hide_index=True, use_container_width=True,
                         column_config={"PRODUTO": st.column_config.TextColumn(width=600)})
