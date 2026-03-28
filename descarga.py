import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

# 1. Função Robusta para formatar moeda no padrão Brasileiro (R$ 1.234,56)
def formatar_moeda(valor):
    try:
        # Se nulo ou não numérico, trata como zero
        if pd.isna(valor): valor = 0.0
        # Garante que é float
        num_valor = float(valor)
        if num_valor == 0: return "R$ 0,00"
        
        texto = f"{num_valor:,.2f}"
        texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"
    except Exception as e:
        # st.error(f"Erro formatação moeda: {e}") # Debugging silenciado
        return "R$ 0,00"

# 2. Função Robusta para corrigir o EAN e evitar notação científica (Retira o 7,90E+12)
def corrigir_ean(valor):
    if pd.isna(valor) or str(valor).strip() == "" or str(valor).lower() == "nan":
        return ""
    try:
        # Handle possible scientific notation artifacts in string
        val_str = str(valor).strip().replace(',', '.')
        return f"{float(val_str):.0f}"
    except:
        # Retorna o texto original se ambas conversões falharem
        return str(valor).strip()

@st.cache_data
def load_data():
    try:
        # Lê os ficheiros CSV que estão no seu GitHub
        df_f = pd.read_csv("Faturamento.csv", sep=";", encoding='latin-1', dtype=str) 
        df_v = pd.read_csv("Vendedores.csv", sep=";", encoding='latin-1', dtype=str)
        
        # --- LIMPEZA DE DADOS CRÍTICA ---
        # Converte a coluna de Data (índice 9)
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        
        # --- BLINDAGEM NUMÉRICA ---
        # Convertemos as colunas de VALOR (índice 22) e PESO (índice 26) para números reais (float).
        # Trocamos vírgulas decimais por pontos padrão do Python antes da conversão.
        df_f['VALOR_NUM'] = pd.to_numeric(
            df_f.iloc[:, 22].astype(str).str.strip().str.replace(',', '.'), 
            errors='coerce'
        ).fillna(0.0)
        
        df_f['PESO_NUM'] = pd.to_numeric(
            df_f.iloc[:, 26].astype(str).str.strip().str.replace(',', '.'), 
            errors='coerce'
        ).fillna(0.0)
        
        # --- CORREÇÃO DO EAN ---
        df_f.iloc[:, 14] = df_f.iloc[:, 14].apply(corrigir_ean)
        
        # --- LÓGICA PARA RETIRAR REDUNDÂNCIA DO PRODUTO (JÁ COM FABRICANTE) ---
        # Remove o nome do fabricante (Col 7) de dentro da descrição do produto (Col 15)
        def limpar_descricao(row):
            prod = str(row.iloc[15]).strip()
            fab = str(row.iloc[7]).strip()
            if fab != "" and fab != "nan" and fab.lower() in prod.lower():
                # Remove o fabricante, ignorando maiúsculas/minúsculas
                import re
                prod_limpo = re.sub(re.escape(fab), '', prod, flags=re.IGNORECASE)
                return prod_limpo.replace(' - ', ' ').strip()
            return prod

        df_f.iloc[:, 15] = df_f.apply(limpar_descricao, axis=1)
        
        df_f = df_f.dropna(subset=['DATA_FILTRO'])
        return df_f, df_v
    except Exception as e:
        st.error(f"Erro ao ler os ficheiros CSV: {e}")
        return None, None

df_fat, df_vend = load_data()

if df_fat is not None:
    # --- BARRA LATERAL ---
    with st.sidebar:
        st.header("📌 Filtros")
        # Data padrão para testes (pode alterar conforme necessário)
        data_sel = st.date_input("Data da Descarga", value=date(2026, 3, 26), format="DD/MM/YYYY")
        
        vendedores_lista = sorted(df_vend.iloc[:, 1].dropna().unique().tolist())
        nome_vend = st.selectbox("Selecione o Vendedor", vendedores_lista)
        
        # Pega o código do vendedor selecionado
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()
        nome_vend_limpo = str(nome_vend).strip()

    # --- FILTRAGEM ---
    # Busca por Data e por Código do Vendedor (Coluna índice 1) OU Nome do Vendedor (Coluna índice 2)
    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           (
               (df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
               (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend_limpo)
           )
           
    df_filtrado = df_fat[mask].copy()

    # REMOÇÃO DE DUPLICIDADES (Pelo Pedido e Nome do Produto já limpo)
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    # --- PARTE SUPERIOR: RESUMO DOS PEDIDOS DO DIA ---
    st.subheader("📋 Resumo dos Pedidos do Dia")
    
    if df_filtrado.empty:
        st.warning(f"Nenhum pedido encontrado para {nome_vend} em {data_sel.strftime('%d/%m/%Y')}")
    else:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', # Cód Cli
            df_filtrado.columns[5]: 'first', # Cliente
            'VALOR_NUM': 'sum',              # Soma do Valor Limpo
            df_filtrado.columns[11]: 'first',# NFe
            df_filtrado.columns[8]: 'first'  # Hora
        }).reset_index()
        
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        # CÁLCULO DOS TOTAIS DO DIA
        v_total = df_resumo['VALOR'].sum()
        p_total = df_filtrado['PESO_NUM'].sum()
        
        c1, c2 = st.columns(2)
        c1.metric("TOTAL VENDAS", formatar_moeda(v_total))
        
        # Formatação do Peso Localizado (com segurança numérica)
        p_total_formatado = f"{float(p_total):,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
        c2.metric("PESO TOTAL", f"{p_total_formatado} kg")

        # Tabela Principal
        df_display = df_resumo.copy()
        df_display['VALOR'] = df_display['VALOR'].apply(formatar_moeda)
        # Formata a Hora para exibir apenas HH:MM
        df_display['HORA'] = pd.to_datetime(df_display['HORA'], errors='coerce').dt.strftime('%H:%M')

        # AJUSTE DE LARGURA: Aumentado CLIENTE para 400px, Código reduzido
        selecao = st.dataframe(
            df_display, 
            use_container_width=True, 
            hide_index=True, 
            on_select="rerun", 
            selection_mode="single-row",
            column_config={
                "PEDIDO": st.column_config.TextColumn(width="small"),
                "COD_CLI": st.column_config.TextColumn(width="small"),
                "CLIENTE": st.column_config.TextColumn(width=400), # Explicitly larger
                "VALOR": st.column_config.TextColumn(width="medium"),
                "HORA": st.column_config.TextColumn(width="small"),
                "NFE": st.column_config.TextColumn(width="small")
            }
        )

        st.divider() 

        # --- PARTE INFERIOR: DETALHE DO PEDIDO SELECIONADO ---
        st.subheader("🔍 Detalhe do Pedido Selecionado")
        
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_pedido = df_resumo.iloc[idx]['PEDIDO'] 
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_pedido]
            
            # Recupera Coligação (Índice 6)
            coligacao = df_itens.iloc[0, 6]
            colig_txt = coligacao if pd.notna(coligacao) and str(coligacao).strip() != "" else "NÃO TEM COLIGAÇÃO"

            # Cabeçalho dos Boxes de Informação (Blindados para não ficarem brancos)
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.info(f"**Cliente:** {df_itens.iloc[0, 5]}\n\n**Pedido:** {num_pedido}")
            with col_info2:
                st.warning(f"**Coligação:** {colig_txt}\n\n**NF-e:** {df_itens.iloc[0, 11]}")
            with col_info3:
                val_ped = df_itens['VALOR_NUM'].sum()
                pes_ped = df_itens['PESO_NUM'].sum()
                st.success(f"**Valor Pedido:** {formatar_moeda(val_ped)}")
                # KPI de peso no detalhe (Formatação segura para evitar ValueError da imagem)
                p_ped_formatado = f"{float(pes_ped):,.3f}".replace(".", ",") # thousands.decimal -> thousands,decimal
                st.success(f"**Peso Pedido:** {p_ped_formatado} kg")

            # Tabela de Itens (Colunas: 13, 15, 7, 19, 20, VALOR_NUM, PESO_NUM, 14)
            df_det = pd.DataFrame({
                'CÓDIGO': df_itens.iloc[:, 13],
                'PRODUTO': df_itens.iloc[:, 15],
                'FABRICANTE': df_itens.iloc[:, 7],
                'CX': df_itens.iloc[:, 19],
                'UN': df_itens.iloc[:, 20],
                'VALOR': df_itens['VALOR_NUM'].apply(formatar_moeda),
                'PESO': df_itens['PESO_NUM'].apply(lambda x: f"{x:,.3f} kg".replace(".", ",")),
                'EAN': df_itens.iloc[:, 14] # Já corrigido no load_data
            })
            
            # Ajuste de Largura no Detalhe: Código reduzido, Produto aumentado
            st.dataframe(
                df_det, 
                hide_index=True, 
                use_container_width=True,
                column_config={
                    "CÓDIGO": st.column_config.TextColumn(width="small"),
                    "PRODUTO": st.column_config.TextColumn(width="large"),
                    "FABRICANTE": st.column_config.TextColumn(width="medium"),
                    "VALOR": st.column_config.TextColumn(width="medium"),
                    "EAN": st.column_config.TextColumn(width="medium")
                }
            )
        else:
            st.info("👆 Clique em uma linha da tabela acima para ver os produtos.")
