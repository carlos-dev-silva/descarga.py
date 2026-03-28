import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# Função para formatar moeda no padrão Brasileiro (R$ 1.234,56)
def formatar_moeda(valor):
    try:
        # Formata com 2 casas decimais e separador de milhar americano
        texto = f"{valor:,.2f}"
        # Troca a vírgula por um 'X' temporário, o ponto por vírgula, e o 'X' por ponto
        texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"
    except:
        return "R$ 0,00"

def load_data():
    try:
        df_f = pd.read_excel("Descargas_Teste.xlsm", sheet_name="Faturamento")
        df_v = pd.read_excel("Descargas_Teste.xlsm", sheet_name="Vendedores")
        
        # Cria a coluna de data segura
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        df_f = df_f.dropna(subset=['DATA_FILTRO'])
        
        return df_f, df_v
    except Exception as e:
        st.error(f"Erro ao ler o arquivo Excel: {e}")
        return None, None

df_fat, df_vend = load_data()

if df_fat is not None:
    # --- BARRA LATERAL ---
    with st.sidebar:
        st.header("📌 Filtros")
        
        # Filtro de data no padrão Brasileiro
        data_sel = st.date_input("Data da Descarga", value=date(2026, 3, 16), format="DD/MM/YYYY")
        
        # Vendedores em ordem alfabética
        vendedores_lista = df_vend.iloc[:, 1].dropna().unique().tolist()
        vendedores_ordenados = sorted(vendedores_lista) # ORDENAÇÃO A-Z
        
        nome_vend = st.selectbox("Selecione o Vendedor", vendedores_ordenados)
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()

    # --- FILTRAGEM ---
    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           (df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend)
           
    df_filtrado = df_fat[mask].copy()

    # ==============================================================================
    # PARTE SUPERIOR: RESUMO DOS PEDIDOS DO DIA
    # ==============================================================================
    st.subheader("📋 Resumo dos Pedidos do Dia")
    
    if df_filtrado.empty:
        st.warning(f"Nenhum pedido encontrado para {nome_vend} na data {data_sel.strftime('%d/%m/%Y')}")
    else:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', # Cód Cliente
            df_filtrado.columns[5]: 'first', # Cliente
            df_filtrado.columns[24]: 'first', # Valor
            df_filtrado.columns[11]: 'first', # NFe
            df_filtrado.columns[8]: 'first'  # Hora
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        # Calcula Totais antes de formatar para texto
        v_total = df_resumo['VALOR'].sum()
        p_total = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[13]])[df_filtrado.columns[26]].sum()
        
        # Exibe os totais do dia
        c1, c2, c3 = st.columns([1, 1, 2])
        c1.metric("TOTAL VENDAS", formatar_moeda(v_total))
        c2.metric("PESO TOTAL DO DIA", f"{p_total:,.3f} kg".replace(".", ","))

        # FORMATANDO A TABELA DE VISUALIZAÇÃO (Strings para ficar bonito na tela)
        df_display = df_resumo.copy()
        df_display['VALOR'] = df_display['VALOR'].apply(formatar_moeda)
        # Formata a HORA para HH:MM (ignora a data e os segundos)
        df_display['HORA'] = pd.to_datetime(df_display['HORA'], errors='coerce').dt.strftime('%H:%M')

        # Tabela Master (Ocupa a largura toda)
        selecao = st.dataframe(
            df_display, 
            use_container_width=True, 
            hide_index=True, 
            on_select="rerun", 
            selection_mode="single-row"
        )

        st.divider() # Uma linha divisória para separar visualmente as duas seções

        # ==============================================================================
        # PARTE INFERIOR: DETALHES DO PEDIDO SELECIONADO
        # ==============================================================================
        st.subheader("🔍 Detalhe do Pedido")
        
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_pedido = df_resumo.iloc[idx]['PEDIDO'] # Pega do df original (não formatado)
            
            # Filtra os produtos daquele pedido específico
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_pedido]
            
            # --- CABEÇALHO DO DETALHE DO PEDIDO (IGUAL AO SEU EXCEL) ---
            # Extraindo variáveis para o cabeçalho
            cliente = df_itens.iloc[0, 5]
            # No seu VBA, Coligação estava na coluna G (índice 6)
            coligacao = df_itens.iloc[0, 6] 
            if pd.isna(coligacao) or str(coligacao).strip() == "" or coligacao == 0:
                coligacao = "NÃO TEM COLIGAÇÃO"
                
            nfe = df_itens.iloc[0, 11] # Coluna L
            valor_ped = df_itens.iloc[0, 24] # Coluna Y
            peso_ped = df_itens.drop_duplicates(subset=[df_itens.columns[13]])[df_itens.columns[26]].sum()
            origem = df_itens.iloc[0, 27] # Coluna AB
            
            # Renderiza as caixas de informação do cabeçalho
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.info(f"**Cliente:** {cliente}\n\n**Nº Pedido:** {num_pedido}")
            with col_info2:
                st.warning(f"**Coligação:** {coligacao}\n\n**NF-e:** {nfe}")
            with col_info3:
                st.success(f"**Valor do Pedido:** {formatar_moeda(valor_ped)}\n\n**Peso do Pedido:** {peso_ped:,.3f} kg".replace(".", ","))
            
            st.markdown(f"**Origem:** {origem}")

            # --- TABELA DE PRODUTOS ---
            # Colunas: Cod(13), Desc(15), Fab(7), Cx(19), Un(20), Val(22), Peso(26), EAN(14)
            df_det = df_itens.iloc[:, [13, 15, 7, 19, 20, 22, 26, 14]].copy()
            df_det.columns = ['CÓDIGO', 'PRODUTO', 'FABRICANTE', 'CAIXAS', 'UNIDADES', 'VALOR', 'PESO', 'EAN']
            
            # Formata Valor e Peso dos itens para visualização
            df_det['VALOR'] = df_det['VALOR'].apply(formatar_moeda)
            df_det['PESO'] = df_det['PESO'].apply(lambda x: f"{x:,.3f} kg".replace(".", ","))
            
            # Mostra a tabela detalhada
            st.dataframe(df_det, hide_index=True, use_container_width=True)
            
        else:
            st.info("👆 Clique em um pedido na tabela acima para visualizar os produtos e detalhes.")