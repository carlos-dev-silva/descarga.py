import streamlit as st
import pandas as pd
from datetime import date
import re
import io
from fpdf import FPDF

st.set_page_config(layout="wide", page_title="Dashboard de Descarga")

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
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(190, 10, txt=titulo_doc, ln=1, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 8)
    # Define larguras fixas simples para caber na folha
    pdf.cell(30, 8, "PEDIDO", 1)
    pdf.cell(100, 8, "CLIENTE", 1)
    pdf.cell(30, 8, "VALOR", 1)
    pdf.cell(30, 8, "HORA", 1)
    pdf.ln()

    pdf.set_font("Arial", '', 8)
    for _, row in df.iterrows():
        pdf.cell(30, 8, str(row['PEDIDO']), 1)
        pdf.cell(100, 8, str(row['CLIENTE'])[:50], 1)
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
    # --- FILTROS LATERAIS ---
    with st.sidebar:
        st.header("📌 Filtros")
        data_sel = st.date_input("Data da Descarga", value=date(2026, 3, 10), format="DD/MM/YYYY")
        vendedores = sorted(df_vend.iloc[:, 1].dropna().unique().tolist())
        nome_vend = st.selectbox("Selecione o Vendedor", vendedores)
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()

    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           ((df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
            (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend))
    
    df_filtrado = df_fat[mask].copy()
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    st.subheader("📋 Resumo dos Pedidos do Dia")
    
    if not df_filtrado.empty:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', df_filtrado.columns[5]: 'first',
            'VALOR_NUM': 'sum', df_filtrado.columns[11]: 'first', df_filtrado.columns[8]: 'first'
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']

        # 1. KPIs (Indicadores)
        kpi1, kpi2 = st.columns(2)
        kpi1.metric("TOTAL VENDAS", formatar_moeda(df_resumo['VALOR'].sum()))
        p_tot = df_filtrado['PESO_NUM'].sum()
        kpi2.metric("PESO TOTAL", f"{p_tot:,.3f} kg".replace(".", ","))

        # 2. BOTÕES ALINHADOS À DIREITA (Abaixo dos KPIs)
        # Criamos 4 colunas. A primeira é um "espaçador" gigante.
        espaco, col_ex, col_pdf = st.columns([5, 1.2, 1.2])
        
        with col_ex:
            btn_excel = para_excel(df_resumo)
            st.download_button("📥 Excel", btn_excel, f"Resumo_{nome_vend}.xlsx", use_container_width=True)
        with col_pdf:
            # Preparamos o PDF com o valor formatado para o arquivo
            df_pdf = df_resumo.copy()
            df_pdf['VALOR'] = df_pdf['VALOR'].apply(formatar_moeda)
            btn_pdf = para_pdf(df_pdf, f"Resumo de Carga - {nome_vend}")
            st.download_button("📄 PDF", btn_pdf, f"Resumo_{nome_vend}.pdf", use_container_width=True)

        # 3. TABELA DE RESUMO
        df_disp = df_resumo.copy()
        df_disp['VALOR'] = df_disp['VALOR'].apply(formatar_moeda)
        selecao = st.dataframe(df_disp, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row",
                               column_config={"CLIENTE": st.column_config.TextColumn(width=600)})

        # 4. DETALHE DO PEDIDO
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_ped = df_resumo.iloc[idx]['PEDIDO']
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_ped]
            
            st.divider()
            st.subheader(f"🔍 Detalhes: {num_ped}")
            df_det = pd.DataFrame({
                'CÓDIGO': df_itens.iloc[:, 13], 
                'PRODUTO': df_itens.iloc[:, 15],
                'FABRICANTE': df_itens.iloc[:, 7],
                'CX': df_itens.iloc[:, 19].astype(str), 
                'UN': df_itens.iloc[:, 20].astype(str),
                'VALOR': df_itens['VALOR_NUM'].apply(formatar_moeda)
            })
            st.dataframe(df_det, hide_index=True, use_container_width=True,
                         column_config={"PRODUTO": st.column_config.TextColumn(width=500)})
