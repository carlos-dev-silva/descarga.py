import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# 1. Função para formatar moeda no padrão Brasileiro
def formatar_moeda(valor):
    try:
        texto = f"{valor:,.2f}"
        texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"
    except:
        return "R$ 0,00"

# 2. Função para carregar os dados (CORRIGIDA COM ENCODING LATIN-1)
@st.cache_data
def load_data():
    try:
        # Adicionamos encoding='latin-1' para aceitar acentos do Excel (Ex: "Promoção")
        df_f = pd.read_csv("Faturamento.csv", sep=";", encoding='latin-1') 
        df_v = pd.read_csv("Vendedores.csv", sep=";", encoding='latin-1')
        
        # Ajuste da coluna de data (Coluna de índice 9)
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        df_f = df_f.dropna(subset=['DATA_FILTRO'])
        
        return df_f, df_v
    except Exception as e:
        st.error(f"Erro ao ler os arquivos: {e}")
        return None, None

df_fat, df_vend = load_data()

if df_fat is not None:
    # --- BARRA LATERAL (FILTROS) ---
    with st.sidebar:
        st.header("📌 Filtros")
        # Ajuste a data para uma que você saiba que tem dados (Ex: 26/03/2026)
        data_sel = st.date_input("Data da Descarga", value=date(2026, 3, 26), format="DD/MM/YYYY")
        
        vendedores_lista = df_vend.iloc[:, 1].dropna().unique().tolist()
        vendedores_ordenados = sorted(vendedores_lista)
        
        nome_vend = st.selectbox("Selecione o Vendedor", vendedores_ordenados)
        
        # Pega código e nome para busca dupla (igual ao seu VBA)
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()
        nome_vend_limpo = str(nome_vend).strip()

    # --- FILTRAGEM ---
    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           (
               (df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
               (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend_limpo)
           )
           
    df_filtrado = df_fat[mask].copy()

    # --- REMOÇÃO DE DUPLICIDADES (Pelo Pedido e Nome do Produto) ---
    # Isso garante que SKUs diferentes não sejam apagados, mas linhas repetidas do ERP sim.
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    # --- PARTE SUPERIOR: RESUMO ---
    st.subheader("📋 Resumo dos Pedidos do Dia")
    
    if df_filtrado.empty:
        st.warning(f"Nenhum pedido encontrado para {nome_vend} em {data_sel.strftime('%d/%m/%Y')}")
    else:
        # Agrupamento para a tabela de cima
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', # Cód Cliente
            df_filtrado.columns[5]: 'first', # Cliente
            df_filtrado.columns[22]: 'sum',  # Soma Real dos SKUs
            df_filtrado.columns[11]: 'first', # NFe
            df_filtrado.columns[8]: 'first'  # Hora
        }).reset_index()
        
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        # Totais (KPIs)
        v_total = df_resumo['VALOR'].sum()
        p_total = df_filtrado[df_filtrado.columns[26]].sum()
        
        c1, c2, c3 = st.columns([1, 1, 2])
        c1.metric("TOTAL VENDAS", formatar_moeda(v_total))
        c2.metric("PESO TOTAL", f"{p_total:,.3f} kg".replace(".", ","))

        # Tabela Principal
        df_display = df_resumo.copy()
        df_display['VALOR'] = df_display['VALOR'].apply(formatar_moeda)
        df_display['HORA'] = pd.to_datetime(df_display['HORA'], errors='coerce').dt.strftime('%H:%M')

        selecao = st.dataframe(
            df_display, 
            use_container_width=True, 
            hide_index=True, 
            on_select="rerun", 
            selection_mode="single-row"
        )

        st.divider() 

        # --- PARTE INFERIOR: DETALHES ---
        st.subheader("🔍 Detalhe do Pedido Selecionado")
        
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_pedido = df_resumo.iloc[idx]['PEDIDO'] 
            
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_pedido]
            
            # Cabeçalho do Detalhe
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.info(f"**Cliente:** {df_itens.iloc[0, 5]}\n\n**Pedido:** {num_pedido}")
            with col_info2:
                st.warning(f"**NF-e:** {df_itens.iloc[0, 11]}")
            with col_info3:
                val_ped = df_itens.iloc[:, 22].sum()
                st.success(f"**Total Pedido:** {formatar_moeda(val_ped)}")

            # Tabela de Itens
            df_det = df_itens.iloc[:, [13, 15, 7, 19, 20, 22, 26, 14]].copy()
            df_det.columns = ['CÓDIGO', 'PRODUTO', 'FABRICANTE', 'CX', 'UN', 'VALOR', 'PESO', 'EAN']
            df_det['VALOR'] = df_det['VALOR'].apply(formatar_moeda)
            
            st.dataframe(df_det, hide_index=True, use_container_width=True)
        else:
            st.info("👆 Clique em uma linha da tabela de resumo para ver os produtos.")
