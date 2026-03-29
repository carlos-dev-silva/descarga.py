import streamlit as st
import pandas as pd
from datetime import date
import re

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# 1. Função de Formatação de Moeda (Padrão Brasileiro)
def formatar_moeda(valor):
    try:
        val = float(valor)
        if val == 0: return "R$ 0,00"
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

# 2. FUNÇÃO MESTRA DE LIMPEZA NUMÉRICA (Resolve o problema do R$ 0,00 e Peso 0)
def limpar_para_numero(valor):
    if pd.isna(valor): return 0.0
    s = str(valor).strip().replace('R$', '').replace(' ', '')
    if not s or s.lower() == 'nan': return 0.0
    try:
        # Se o número vem como 1.234,56 -> tira o ponto e troca a vírgula por ponto
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        # Se vem apenas 1234,56 -> troca a vírgula por ponto
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except:
        return 0.0

# 3. FUNÇÃO PARA O EAN (Remove o 7,90E+12)
def limpar_ean(valor):
    if pd.isna(valor) or str(valor).strip() == "": return ""
    try:
        # Converte para float e depois para string sem casas decimais
        return f"{float(valor):.0f}"
    except:
        return str(valor).strip().split('.')[0]

@st.cache_data
def load_data():
    try:
        # Lê os CSVs do seu GitHub
        df_f = pd.read_csv("Faturamento.csv", sep=";", encoding='latin-1', dtype=str) 
        df_v = pd.read_csv("Vendedores.csv", sep=";", encoding='latin-1', dtype=str)
        
        # Limpeza de Data
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        
        # Limpeza Numérica (Valor e Peso)
        df_f['VALOR_NUM'] = df_f.iloc[:, 22].apply(limpar_para_numero)
        df_f['PESO_NUM'] = df_f.iloc[:, 26].apply(limpar_para_numero)
        
        # Limpeza de EAN
        df_f.iloc[:, 14] = df_f.iloc[:, 14].apply(limpar_ean)
        
        # --- LIMPEZA DO PRODUTO (Retirar Fabricante da Descrição) ---
        def remover_fabricante(row):
            prod = str(row.iloc[15]).strip()
            fab = str(row.iloc[7]).strip()
            if fab.lower() in prod.lower():
                # Remove o nome do fabricante da descrição
                regex = re.compile(re.escape(fab), re.IGNORECASE)
                res = regex.sub('', prod)
                return res.replace(' - ', ' ').strip()
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

    # --- FILTRAGEM ---
    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           ((df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
            (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend))
    
    df_filtrado = df_fat[mask].copy()
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    # --- DASHBOARD ---
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

        # KPIs
        c1, c2 = st.columns(2)
        c1.metric("TOTAL VENDAS", formatar_moeda(df_resumo['VALOR'].sum()))
        p_total = df_filtrado['PESO_NUM'].sum()
        c2.metric("PESO TOTAL", f"{p_total:,.3f} kg".replace(",", "X").replace(".", ",").replace("X", "."))

        # Tabela Principal com larguras ajustadas
        df_display = df_resumo.copy()
        df_display['VALOR'] = df_display['VALOR'].apply(formatar_moeda)
        
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
                "CLIENTE": st.column_config.TextColumn(width="large"), # AUMENTADO
                "VALOR": st.column_config.TextColumn(width="medium"),
                "NFE": st.column_config.TextColumn(width="small")
            }
        )

        st.divider() 

        # --- DETALHE ---
        st.subheader("🔍 Detalhe do Pedido Selecionado")
        
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_pedido = df_resumo.iloc[idx]['PEDIDO'] 
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_pedido]
            
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.info(f"**Cliente:** {df_itens.iloc[0, 5]}\n\n**Pedido:** {num_pedido}")
            with col_info2:
                colig = df_itens.iloc[0, 6]
                st.warning(f"**Coligação:** {colig if pd.notna(colig) else 'NÃO TEM'}\n\n**NF-e:** {df_itens.iloc[0, 11]}")
            with col_info3:
                v_ped = df_itens['VALOR_NUM'].sum()
                p_ped = df_itens['PESO_NUM'].sum()
                st.success(f"**Valor:** {formatar_moeda(v_ped)}\n\n**Peso:** {p_ped:,.3f} kg".replace(".", ","))

            # Tabela de Detalhes
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
                    "CÓDIGO": st.column_config.TextColumn(width="small"), # REDUZIDO
                    "PRODUTO": st.column_config.TextColumn(width="large"), # AUMENTADO
                    "FABRICANTE": st.column_config.TextColumn(width="medium"),
                    "EAN": st.column_config.TextColumn(width="medium")
                }
            )
