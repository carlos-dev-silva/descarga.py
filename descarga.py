import streamlit as st
import pandas as pd
from datetime import date
import re
import io
from fpdf import FPDF

# Configuração da página
st.set_page_config(layout="wide", page_title="CCN - Dashboard de Descarga", page_icon="📊")

# --- ESTILIZAÇÃO CSS (Visual Moderno do Dashboard) ---
st.markdown("""
    <style>
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px 20px;
        border-radius: 12px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.05);
    }
    div[data-testid="stMetricLabel"] {
        font-size: 14px !important;
        color: #666666 !important;
        font-weight: bold;
    }
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

# --- CLASSE CUSTOMIZADA PARA PDF PROFISSIONAL ---
class PDF(FPDF):
    def header(self):
        # Logo CCN
        try:
            self.image('sem_fundo.png', 10, 8, 33)
        except:
            pass
        self.set_font('Arial', 'B', 15)
        self.cell(80)
        self.cell(30, 10, 'RELATÓRIO DE CARGA OPERACIONAL', 0, 0, 'C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()} | Gerado em {date.today().strftime("%d/%m/%Y")}', 0, 0, 'C')

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
        if ',' in s and '.' in s: s = s.replace('.', '').replace(',', '.')
        elif ',' in s: s = s.replace(',', '.')
        return float(s)
    except: return 0.0

# --- EXPORTAÇÃO PDF TURBO ---
def gerar_pdf_completo(df, vendedor, data_doc, faturamento, peso, qtd):
    pdf = PDF()
    pdf.add_page()
    
    # Box de Informações do Filtro
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(190, 10, f" Vendedor: {vendedor} | Data da Descarga: {data_doc}", 1, 1, 'L', fill=True)
    pdf.ln(5)

    # Box de Resumo (KPIs)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(63, 10, "Faturamento Total", 1, 0, 'C')
    pdf.cell(63, 10, "Peso Total", 1, 0, 'C')
    pdf.cell(64, 10, "Pedidos", 1, 1, 'C')
    
    pdf.set_font('Arial', '', 11)
    pdf.cell(63, 10, faturamento, 1, 0, 'C')
    pdf.cell(63, 10, f"{peso:,.2f} kg".replace(".", ","), 1, 0, 'C')
    pdf.cell(64, 10, str(qtd), 1, 1, 'C')
    pdf.ln(10)

    # Tabela de Pedidos
    pdf.set_fill_color(0, 51, 102) # Azul Marinho CCN
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(20, 10, "PEDIDO", 1, 0, 'C', fill=True)
    pdf.cell(20, 10, "CÓD", 1, 0, 'C', fill=True)
    pdf.cell(90, 10, "CLIENTE", 1, 0, 'C', fill=True)
    pdf.cell(30, 10, "VALOR", 1, 0, 'C', fill=True)
    pdf.cell(30, 10, "HORA", 1, 1, 'C', fill=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Arial', '', 8)
    
    for i, row in df.iterrows():
        # Efeito de linhas alternadas (zebrado)
        fill = True if i % 2 == 0 else False
        pdf.set_fill_color(245, 245, 245)
        
        pdf.cell(20, 8, str(row['PEDIDO']), 1, 0, 'C', fill=fill)
        pdf.cell(20, 8, str(row['COD_CLI']), 1, 0, 'C', fill=fill)
        pdf.cell(90, 8, str(row['CLIENTE'])[:55], 1, 0, 'L', fill=fill)
        pdf.cell(30, 8, str(row['VALOR']), 1, 0, 'C', fill=fill)
        pdf.cell(30, 8, str(row['HORA']), 1, 1, 'C', fill=fill)
        
    return pdf.output(dest='S').encode('latin-1')

# --- EXPORTAÇÃO EXCEL ---
def para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Resumo')
    return output.getvalue()

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
    with st.sidebar:
        try: st.image("sem_fundo.png", use_container_width=True)
        except: pass
        st.write("---")
        data_sel = st.date_input("🗓️ Data da Descarga", value=date(2026, 3, 10), format="DD/MM/YYYY")
        vendedores = sorted(df_vend.iloc[:, 1].dropna().unique().tolist())
        nome_vend = st.selectbox("👤 Vendedor", vendedores)
        cod_vend = str(df_vend[df_vend.iloc[:, 1] == nome_vend].iloc[0, 0]).strip()
        st.divider()
        st.caption("v3.0 - Dashboard CCN")

    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           ((df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
            (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend))
    
    df_filtrado = df_fat[mask].copy()
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    if not df_filtrado.empty:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', # COD_CLI
            df_filtrado.columns[5]: 'first', # CLIENTE
            'VALOR_NUM': 'sum', 
            df_filtrado.columns[11]: 'first', 
            df_filtrado.columns[8]: 'first',
            df_filtrado.columns[6]: 'first'  
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA', 'COLIGACAO']

        # --- CABEÇALHO ---
        head1, head2, head3 = st.columns([4, 1, 1])
        with head1:
            st.title("📋 Resumo Operacional")
            st.write(f"Vendedor: **{nome_vend}** | Data: **{data_sel.strftime('%d/%m/%Y')}**")
        
        # Preparação dos Dados de Resumo para Exportação
        fat_total_str = formatar_moeda(df_resumo['VALOR'].sum())
        peso_total = df_filtrado['PESO_NUM'].sum()
        qtd_pedidos = len(df_resumo)
        
        with head2:
            st.write("##")
            btn_excel = para_excel(df_resumo[['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']])
            st.download_button("📥 Excel", btn_excel, f"Resumo_{nome_vend}.xlsx", use_container_width=True)
        with head3:
            st.write("##")
            df_pdf = df_resumo.copy()
            df_pdf['VALOR'] = df_pdf['VALOR'].apply(formatar_moeda)
            # NOVO PDF COMPLETO
            btn_pdf = gerar_pdf_completo(df_pdf, nome_vend, data_sel.strftime('%d/%m/%Y'), fat_total_str, peso_total, qtd_pedidos)
            st.download_button("📄 PDF", btn_pdf, f"Relatorio_{nome_vend}.pdf", use_container_width=True)

        st.divider()

        # --- KPIs ---
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Faturamento Total", fat_total_str)
        m2.metric("Peso Total (kg)", f"{peso_total:,.2f}".replace(".", ","))
        m3.metric("Qtd. Pedidos", qtd_pedidos)
        m4.metric("Ticket Médio", formatar_moeda(df_resumo['VALOR'].mean()))

        st.write("###")

        # --- TABELA DE RESUMO ---
        df_disp = df_resumo[['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']].copy()
        df_disp['VALOR'] = df_disp['VALOR'].apply(formatar_moeda)
        selecao = st.dataframe(
            df_disp, use_container_width=True, hide_index=True, 
            on_select="rerun", selection_mode="single-row",
            column_config={
                "COD_CLI": st.column_config.TextColumn("Cód. Cliente", width="small"),
                "CLIENTE": st.column_config.TextColumn("Nome do Cliente", width=600),
                "PEDIDO": st.column_config.TextColumn("Nº Pedido", width="small")
            }
        )

        # --- DETALHE DO PEDIDO SELECIONADO ---
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_ped = df_resumo.iloc[idx]['PEDIDO']
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_ped]
            
            st.write("###")
            c_det1, c_det2, c_det3 = st.columns(3)
            with c_det1:
                st.info(f"**Cliente:** {df_itens.iloc[0, 5]}\n\n**Pedido:** {num_ped}")
            with c_det2:
                colig = df_itens.iloc[0, 6]
                st.warning(f"**Coligação:** {colig if pd.notna(colig) and str(colig).lower() != 'nan' else 'NÃO TEM'}\n\n**NF-e:** {df_itens.iloc[0, 11]}")
            with c_det3:
                val_ped = df_itens['VALOR_NUM'].sum()
                pes_ped = df_itens['PESO_NUM'].sum()
                st.success(f"**Valor:** {formatar_moeda(val_ped)}\n\n**Peso:** {pes_ped:,.3f} kg".replace(".", ","))

            with st.container(border=True):
                st.subheader(f"🔍 Itens do Pedido: {num_ped}")
                df_det = pd.DataFrame({
                    'CÓDIGO': df_itens.iloc[:, 13], 
                    'PRODUTO': df_itens.iloc[:, 15],
                    'FABRICANTE': df_itens.iloc[:, 7],
                    'CX': df_itens.iloc[:, 19].astype(str), 
                    'UN': df_itens.iloc[:, 20].astype(str),
                    'VALOR': df_itens['VALOR_NUM'].apply(formatar_moeda),
                    'PESO': df_itens['PESO_NUM'].apply(lambda x: f"{x:,.3f} kg".replace(".", ","))
                })
                st.dataframe(
                    df_det, hide_index=True, use_container_width=True,
                    column_config={"PRODUTO": st.column_config.TextColumn(width=600)}
                )
