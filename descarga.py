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

@st.cache_data
def load_data():
    try:
        df_f = pd.read_excel("Descargas_Teste.xlsm", sheet_name="Faturamento")
        df_v = pd.read_excel("Descargas_Teste.xlsm", sheet_name="Vendedores")
        
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        df_f = df_f.dropna(subset=['DATA_FILTRO'])
        
        return df_f, df_v
    except Exception as e:
        st.error(f"Erro ao ler o ficheiro Excel: {e}")
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

    # 🚨 A CORREÇÃO MESTRA: REMOVER DUPLICIDADES ANTES DE QUALQUER CÁLCULO 🚨
    # Mantém apenas 1 linha única para cada combinação de "Nº do Pedido" (10) e "Cód Produto" (13)
    # Isso impede que os valores de 457,82 e 44,98 sejam somados 3 vezes!
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[13]])

    # --- PARTE SUPERIOR: RESUMO ---
    st.subheader("📋 Resumo dos Pedidos do Dia")
    
    if df_filtrado.empty:
        st.warning(f"Nenhum pedido encontrado para {nome_vend} na data {data_sel.strftime('%d/%m/%Y')}")
    else:
        # Agora podemos somar os itens com segurança, pois os repetidos já foram apagados
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', # Cód Cliente
            df_filtrado.columns[5]: 'first', # Cliente
            df_filtrado.columns[22]: 'sum',  # VALOR: Soma dos SKUs exatos do pedido
            df_filtrado.columns[11]: 'first', # NFe
            df_filtrado.columns[8]: 'first'  # Hora
        }).reset_index()
        
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        # Totais
        v_total = df_resumo['VALOR'].sum()
        p_total = df_filtrado[df_filtrado.columns[26]].sum() # Como não tem duplicatas, basta somar direto
        
        c1, c2, c3 = st.columns([1, 1, 2])
        c1.metric("TOTAL VENDAS", formatar_moeda(v_total))
        c2.metric("PESO TOTAL DO DIA", f"{p_total:,.3f} kg".replace(".", ","))

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
        st.subheader("🔍 Detalhe do Pedido")
        
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_pedido = df_resumo.iloc[idx]['PEDIDO'] 
            
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_pedido]
            
            cliente = df_itens.iloc[0, 5]
            coligacao = df_itens.iloc[0, 6] 
            if pd.isna(coligacao) or str(coligacao).strip() == "" or coligacao == 0:
                coligacao = "NÃO TEM COLIGAÇÃO"
                
            nfe = df_itens.iloc[0, 11] 
            
            valor_ped = df_itens.iloc[:, 22].sum() 
            peso_ped = df_itens.iloc[:, 26].sum() 
            origem = df_itens.iloc[0, 27] 
            
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.info(f"**Cliente:** {cliente}\n\n**Nº Pedido:** {num_pedido}")
            with col_info2:
                st.warning(f"**Coligação:** {coligacao}\n\n**NF-e:** {nfe}")
            with col_info3:
                st.success(f"**Valor do Pedido:** {formatar_moeda(valor_ped)}\n\n**Peso do Pedido:** {peso_ped:,.3f} kg".replace(".", ","))
            
            st.markdown(f"**Origem:** {origem}")

            df_det = df_itens.iloc[:, [13, 15, 7, 19, 20, 22, 26, 14]].copy()
            df_det.columns = ['CÓDIGO', 'PRODUTO', 'FABRICANTE', 'CAIXAS', 'UNIDADES', 'VALOR', 'PESO', 'EAN']
            
            df_det['VALOR'] = df_det['VALOR'].apply(formatar_moeda)
            df_det['PESO'] = df_det['PESO'].apply(lambda x: f"{x:,.3f} kg".replace(".", ","))
            
            st.dataframe(df_det, hide_index=True, use_container_width=True)
            
        else:
            st.info("👆 Clique num pedido na tabela acima para visualizar os produtos e detalhes.")
