import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# 1. Função para formatar moeda no padrão Brasileiro
def formatar_moeda(valor):
    try:
        if pd.isna(valor): return "R$ 0,00"
        texto = f"{valor:,.2f}"
        texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"
    except:
        return "R$ 0,00"

# 2. Função para carregar e LIMPAR os dados
@st.cache_data
def load_data():
    try:
        # Lendo com latin-1 para evitar erro de acentuação
        df_f = pd.read_csv("Faturamento.csv", sep=";", encoding='latin-1') 
        df_v = pd.read_csv("Vendedores.csv", sep=";", encoding='latin-1')
        
        # --- LIMPEZA DE DADOS CRÍTICA ---
        # Converte a coluna de Data (índice 9)
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        
        # Garante que a coluna de VALOR (índice 22) e PESO (índice 26) sejam números
        # Se houver vírgula no CSV (ex: 10,50), trocamos por ponto para o Python entender
        for col_idx in [22, 26]:
            col_name = df_f.columns[col_idx]
            df_f[col_name] = df_f[col_name].astype(str).str.replace(',', '.')
            df_f[col_name] = pd.to_numeric(df_f[col_name], errors='coerce').fillna(0)
        
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

    # REMOVE DUPLICIDADES (Pelo Pedido e Nome do Produto)
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    # --- PARTE SUPERIOR: RESUMO ---
    st.subheader("📋 Resumo dos Pedidos do Dia")
    
    if df_filtrado.empty:
        st.warning(f"Nenhum pedido encontrado para {nome_vend} em {data_sel.strftime('%d/%m/%Y')}")
    else:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', 
            df_filtrado.columns[5]: 'first', 
            df_filtrado.columns[22]: 'sum',  # Valor Total do Pedido
            df_filtrado.columns[11]: 'first', 
            df_filtrado.columns[8]: 'first'  
        }).reset_index()
        
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        # CÁLCULO DOS TOTAIS
        v_total = df_resumo['VALOR'].sum()
        p_total = df_filtrado[df_filtrado.columns[26]].sum()
        
        c1, c2, c3 = st.columns([1, 1, 2])
        c1.metric("TOTAL VENDAS", formatar_moeda(v_total))
        
        # CORREÇÃO DO ERRO: Garantimos que p_total é float e tratamos o formato com segurança
        p_total_formatado = f"{float(p_total):,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
        c2.metric("PESO TOTAL", f"{p_total_formatado} kg")

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
            
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.info(f"**Cliente:** {df_itens.iloc[0, 5]}\n\n**Pedido:** {num_pedido}")
            with col_info2:
                st.warning(f"**NF-e:** {df_itens.iloc[0, 11]}")
            with col_info3:
                val_ped = df_itens.iloc[:, 22].sum()
                st.success(f"**Total Pedido:** {formatar_moeda(val_ped)}")

            df_det = df_itens.iloc[:, [13, 15, 7, 19, 20, 22, 26, 14]].copy()
            df_det.columns = ['CÓDIGO', 'PRODUTO', 'FABRICANTE', 'CX', 'UN', 'VALOR', 'PESO', 'EAN']
            df_det['VALOR'] = df_det['VALOR'].apply(formatar_moeda)
            
            st.dataframe(df_det, hide_index=True, use_container_width=True)
        else:
            st.info("👆 Clique em uma linha da tabela acima para ver os detalhes.")
