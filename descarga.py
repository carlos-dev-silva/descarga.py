import streamlit as st
import pandas as pd
from datetime import date
import re
import io
from fpdf import FPDF

# Configuração da página - Tema Escuro/Claro automático do Streamlit
st.set_page_config(layout="wide", page_title="CCN - Dashboard de Descarga", page_icon="📊")

# --- ESTILIZAÇÃO CSS (O "Pulo do Gato" para o visual moderno) ---
st.markdown("""
    <style>
    /* Estilizando as métricas (Cards) */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px 20px;
        border-radius: 12px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.05);
    }
    /* Deixando os títulos das métricas mais profissionais */
    div[data-testid="stMetricLabel"] {
        font-size: 14px !important;
        color: #666666 !important;
        font-weight: bold;
    }
    /* Ajustando o corpo do app */
    .main {
        background-color: #f8f9fa;
    }
    /* Estilizando botões de download */
    .stDownloadButton button {
        border-radius: 8px !important;
        border: 1px solid #d1d1d1 !important;
        transition: all 0.3s ease;
    }
    .stDownloadButton button:hover {
        border-color: #007bff !important;
        color: #007bff !important;
        background-color: #f0f7ff !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE APOIO ---
def formatar_moeda(valor):
    try:
        val = float(valor)
        if val == 0: return "R$ 0,00"
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

def limpar_para_numero(valor):
    if pd.isna(valor): return 0.0
    s = str(valor).strip().replace('R$', '').replace(' ', '')
    try:
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except:
        return 0.0

# --- EXPORTAÇÃO ---
def para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Resumo')
    return output.getvalue()

def para_pdf(df, titulo_doc):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(190, 10, txt=titulo_doc, ln=1, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 8)
    pdf.cell(20, 8, "PEDIDO", 1)
    pdf.cell(20, 8, "COD", 1)
    pdf.cell(90, 8, "CLIENTE", 1)
    pdf.cell(30, 8, "VALOR", 1)
    pdf.cell(30, 8, "HORA", 1)
    pdf.ln()
    pdf.set_font("Arial", '', 7)
    for _, row in df.iterrows():
        pdf.cell(20, 8, str(row['PEDIDO']), 1)
        pdf.cell(20, 8, str(row['COD_CLI']), 1)
        pdf.cell(90, 8, str(row['CLIENTE'])[:55], 1)
        pdf.cell(30, 8, str(row['VALOR']), 1)
        pdf.cell(30, 8, str(row['HORA']), 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

@st.cache_data
def load_data():
    try:
        df_f = pd.read_csv("Faturamento.csv", sep=";", encoding='latin-1', dtype=str) 
        df_v = pd.read_csv("Vendedores.csv", sep=";", encoding='latin-1', dtype=str)
        df_f['DATA_FILTRO'] = pd.to_datetime(df_f.iloc[:, 9], dayfirst=True, errors='coerce')
        df_f['VALOR_NUM'] = df_f.iloc[:, 22].apply(limpar_para_numero)
        df_f['PESO_NUM'] = df_f.iloc[:, 26].apply(limpar_para_numero)
        
        def remover_fabricante(row):
            prod, fab = str(row.iloc[15]).strip(), str(row.iloc[7]).strip()
            if fab.lower() in prod.lower():
                return re.sub(re.escape(fab), '', prod, flags=re.IGNORECASE).replace(' - ', ' ').strip()
            return prod
        df_f.iloc[:, 15] = df_f.apply(remover_fabricante, axis=1)
        return df_f.dropna(subset=['DATA_FILTRO']), df_v
    except Exception as e:
        st.error(f"Erro ao carregar: {e}")
        return None, None

df_fat, df_vend = load_data()

if df_fat is not None:
    # --- BARRA LATERAL (Sidebar Estilizada) ---
    with st.sidebar:
        st.title("Settings")
        st.write("Escolha os parâmetros abaixo:")
        data_sel = st.date_input("🗓️ Data da Descarga", value=date(2026, 3, 10), format="DD/MM/YYYY")
        vendedores = sorted(df_vend.iloc[:, 1].dropna().unique().tolist())
        nome_vend = st.selectbox("👤 Vendedor", vendedores)
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()
        st.divider()
        st.caption("v2.0 - Dashboard CCN")

    # Filtro de dados
    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           ((df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
            (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend))
    
    df_filtrado = df_fat[mask].copy()
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    if not df_filtrado.empty:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', 
            df_filtrado.columns[5]: 'first', 
            'VALOR_NUM': 'sum', 
            df_filtrado.columns[11]: 'first', 
            df_filtrado.columns[8]: 'first'
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        # --- CABEÇALHO COM TÍTULO E BOTÕES NO MESMO NÍVEL ---
        head1, head2, head3 = st.columns([4, 1, 1])
        with head1:
            st.title("📋 Resumo Operacional")
            st.write(f"Vendedor: **{nome_vend}** | Data: **{data_sel.strftime('%d/%m/%Y')}**")
        with head2:
            st.write("##") # Alinhamento
            btn_excel = para_excel(df_resumo)
            st.download_button("📥 Excel", btn_excel, f"Resumo_{nome_vend}.xlsx", use_container_width=True)
        with head3:
            st.write("##") # Alinhamento
            df_pdf = df_resumo.copy()
            df_pdf['VALOR'] = df_pdf['VALOR'].apply(formatar_moeda)
            btn_pdf = para_pdf(df_pdf, f"Resumo de Carga - {nome_vend}")
            st.download_button("📄 PDF", btn_pdf, f"Resumo_{nome_vend}.pdf", use_container_width=True)

        st.divider()

        # --- SEÇÃO DE MÉTRICAS (KPIs como Cards) ---
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Faturamento Total", formatar_moeda(df_resumo['VALOR'].sum()))
        p_tot = df_filtrado['PESO_NUM'].sum()
        m2.metric("Peso Total (kg)", f"{p_tot:,.2f}".replace(".", ","))
        m3.metric("Qtd. Pedidos", len(df_resumo))
        m4.metric("Ticket Médio", formatar_moeda(df_resumo['VALOR'].mean()))

        st.write("###")

        # --- TABELA DE RESUMO ---
        df_disp = df_resumo.copy()
        df_disp['VALOR'] = df_disp['VALOR'].apply(formatar_moeda)
        selecao = st.dataframe(
            df_disp, 
            use_container_width=True, 
            hide_index=True, 
            on_select="rerun", 
            selection_mode="single-row",
            column_config={
                "COD_CLI": st.column_config.TextColumn("Cód. Cliente", width="small"),
                "CLIENTE": st.column_config.TextColumn("Nome do Cliente", width=600),
                "PEDIDO": st.column_config.TextColumn("Nº Pedido", width="small"),
                "VALOR": st.column_config.TextColumn("Total Pedido")
            }
        )

        # --- DETALHE DO PEDIDO SELECIONADO ---
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_ped = df_resumo.iloc[idx]['PEDIDO']
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_ped]
            
            st.write("###")
            with st.container(border=True): # Cria um box em volta do detalhe
                st.subheader(f"🔍 Itens do Pedido: {num_ped}")
                
                df_det = pd.DataFrame({
                    'CÓDIGO': df_itens.iloc[:, 13], 
                    'PRODUTO': df_itens.iloc[:, 15],
                    'FABRICANTE': df_itens.iloc[:, 7],
                    'CX': df_itens.iloc[:, 19].astype(str), 
                    'UN': df_itens.iloc[:, 20].astype(str),
                    'VALOR': df_itens['VALOR_NUM'].apply(formatar_moeda)
                })
                st.dataframe(
                    df_det, 
                    hide_index=True, 
                    use_container_width=True,
                    column_config={"PRODUTO": st.column_config.TextColumn(width=600)}
                )
    else:
        st.info("Selecione os filtros na barra lateral para visualizar os dados.")
