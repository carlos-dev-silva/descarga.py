import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# 1. Formatação de Moeda com segurança para nulos
def formatar_moeda(valor):
    try:
        if pd.isna(valor) or valor == 0: return "R$ 0,00"
        texto = f"{valor:,.2f}"
        texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"
    except:
        return "R$ 0,00"

# 2. Função Robusta para limpar números (trata "1.234,56" ou "1234,56")
def limpar_valor(valor):
    if pd.isna(valor): return 0.0
    s = str(valor).strip().replace('R$', '').replace(' ', '')
    if not s: return 0.0
    try:
        # Se tiver ponto e vírgula (ex: 1.234,56), remove o ponto e troca vírgula por ponto
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        # Se tiver apenas vírgula (ex: 1234,56)
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except:
        return 0.0

@st.cache_data
def load_data():
    try:
        # Lendo com latin-1 para evitar erros de acentos brasileiros
        df_f = pd.read_csv("Faturamento.csv", sep=";", encoding='latin-1', dtype=str) 
        df_v = pd.read_csv("Vendedores.csv", sep=";", encoding='latin-1', dtype=str)
        
        # --- LIMPEZA PESADA ---
        # Data (Coluna índice 9)
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        
        # Limpando Valores e Pesos (Índices 22 e 26)
        df_f['VALOR_NUM'] = df_f.iloc[:, 22].apply(limpar_valor)
        df_f['PESO_NUM'] = df_f.iloc[:, 26].apply(limpar_valor)
        
        # EAN (Coluna índice 14) - Força para não ser científico
        df_f.iloc[:, 14] = df_f.iloc[:, 14].fillna('').astype(str).str.split('.').str[0]
        
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
        data_sel = st.date_input("Data da Descarga", value=date(2026, 3, 10), format="DD/MM/YYYY")
        
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

    # Remover duplicatas pelo Pedido (10) e Descrição (15)
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    # --- PARTE SUPERIOR: RESUMO ---
    st.subheader("📋 Resumo dos Pedidos do Dia")
    
    if df_filtrado.empty:
        st.warning("Nenhum pedido encontrado para este filtro.")
    else:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', # Cód Cli
            df_filtrado.columns[5]: 'first', # Cliente
            'VALOR_NUM': 'sum',              # Valor real somado
            df_filtrado.columns[11]: 'first',# NFe
            df_filtrado.columns[8]: 'first'  # Hora
        }).reset_index()
        
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        # KPIs
        v_total = df_resumo['VALOR'].sum()
        p_total = df_filtrado['PESO_NUM'].sum()
        
        c1, c2 = st.columns(2)
        c1.metric("TOTAL VENDAS", formatar_moeda(v_total))
        c2.metric("PESO TOTAL", f"{p_total:,.3f} kg".replace(",", "X").replace(".", ",").replace("X", "."))

        df_display = df_resumo.copy()
        df_display['VALOR'] = df_display['VALOR'].apply(formatar_moeda)
        
        selecao = st.dataframe(df_display, use_container_width=True, hide_index=True, 
                               on_select="rerun", selection_mode="single-row")

        st.divider() 

        # --- PARTE INFERIOR: DETALHES ---
        st.subheader("🔍 Detalhe do Pedido Selecionado")
        
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_pedido = df_resumo.iloc[idx]['PEDIDO'] 
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_pedido]
            
            # Recupera Coligação (Índice 6)
            coligacao = df_itens.iloc[0, 6]
            colig_txt = coligacao if pd.notna(coligacao) and str(coligacao).strip() != "" else "NÃO TEM COLIGAÇÃO"

            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.info(f"**Cliente:** {df_itens.iloc[0, 5]}\n\n**Pedido:** {num_pedido}")
            with col_info2:
                st.warning(f"**Coligação:** {colig_txt}\n\n**NF-e:** {df_itens.iloc[0, 11]}")
            with col_info3:
                val_ped = df_itens['VALOR_NUM'].sum()
                pes_ped = df_itens['PESO_NUM'].sum()
                st.success(f"**Valor Pedido:** {formatar_moeda(val_ped)}\n\n**Peso Pedido:** {pes_ped:,.3f} kg".replace(".", ","))

            # Tabela de Itens (Colunas: 13, 15, 7, 19, 20, VALOR_NUM, PESO_NUM, 14)
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
            st.dataframe(df_det, hide_index=True, use_container_width=True)
