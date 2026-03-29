import streamlit as st
import pandas as pd
from datetime import date
import re
import io
from fpdf import FPDF
import altair as alt

# Configuração da página
st.set_page_config(layout="wide", page_title="CCN - Business Intelligence", page_icon="📈")

# --- ESTILIZAÇÃO CSS ---
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
    }
    </style>
    """, unsafe_allow_html=True)

# --- CLASSE PDF ---
class PDF(FPDF):
    def header(self):
        try: self.image('sem_fundo.png', 10, 8, 33)
        except: pass
        self.set_font('Arial', 'B', 15)
        self.cell(80)
        self.cell(30, 10, 'RELATÓRIO DE PERFORMANCE DE CARGA', 0, 0, 'C')
        self.ln(20)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()} | CCN BI', 0, 0, 'C')

# --- FUNÇÕES ---
def formatar_moeda(valor):
    try:
        val = float(valor)
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "R$ 0,00"

def limpar_para_numero(valor):
    if pd.isna(valor): return 0.0
    s = str(valor).strip().replace('R$', '').replace(' ', '')
    try:
        if ',' in s and '.' in s: s = s.replace('.', '').replace(',', '.')
        elif ',' in s: s = s.replace(',', '.')
        return float(s)
    except: return 0.0

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
        st.error(f"Erro: {e}")
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
        st.caption("v4.1 - CCN Intelligence")

    # Filtro Base
    mask = (df_fat['DATA_FILTRO'].dt.date == data_sel) & \
           ((df_fat.iloc[:, 1].astype(str).str.strip() == cod_vend) | 
            (df_fat.iloc[:, 2].astype(str).str.strip() == nome_vend))
    
    df_filtrado = df_fat[mask].copy()
    df_filtrado = df_filtrado.drop_duplicates(subset=[df_filtrado.columns[10], df_filtrado.columns[15]])

    if not df_filtrado.empty:
        df_resumo = df_filtrado.groupby(df_filtrado.columns[10]).agg({
            df_filtrado.columns[0]: 'first', df_filtrado.columns[5]: 'first',
            'VALOR_NUM': 'sum', df_filtrado.columns[11]: 'first', 
            df_filtrado.columns[8]: 'first', df_filtrado.columns[6]: 'first'  
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA', 'COLIGACAO']

        # --- CABEÇALHO ---
        h1, h2, h3 = st.columns([4, 1, 1])
        with h1:
            st.title("🚀 Performance de Vendas")
            st.write(f"Vendedor: **{nome_vend}** | **{data_sel.strftime('%d/%m/%Y')}**")
        
        with h2:
            st.write("##")
            output_ex = io.BytesIO()
            with pd.ExcelWriter(output_ex, engine='xlsxwriter') as wr:
                df_resumo[['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']].to_excel(wr, index=False)
            st.download_button("📥 Excel", output_ex.getvalue(), f"Resumo_{nome_vend}.xlsx", use_container_width=True)
        
        with h3:
            st.write("##")
            df_pdf = df_resumo.copy()
            df_pdf['VALOR'] = df_pdf['VALOR'].apply(formatar_moeda)
            pdf = PDF()
            pdf.add_page()
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(190, 10, f"Vendedor: {nome_vend} | Faturamento: {formatar_moeda(df_resumo['VALOR'].sum())}", 1, 1, 'C')
            st.download_button("📄 PDF", pdf.output(dest='S').encode('latin-1'), f"Relatorio_{nome_vend}.pdf", use_container_width=True)

        # --- KPIs ---
        st.write("---")
        k1, k2, k3, k4 = st.columns(4)
        total_venda = df_resumo['VALOR'].sum()
        k1.metric("Faturamento", formatar_moeda(total_venda))
        k2.metric("Peso Total", f"{df_filtrado['PESO_NUM'].sum():,.2f} kg".replace(".", ","))
        k3.metric("Pedidos", len(df_resumo))
        k4.metric("Ticket Médio", formatar_moeda(total_venda/len(df_resumo)))

        # --- SEÇÃO DE GRÁFICOS ---
        st.write("### 📊 Análise Visual")
        g1, g2 = st.columns(2)

        with g1:
            st.write("**Top 5 Clientes (R$)**")
            top_clientes = df_resumo.nlargest(5, 'VALOR')
            # Ajuste de altura dinâmica: alt.Step(40) impede que 1 barra fique "gigante"
            chart_cli = alt.Chart(top_clientes).mark_bar(color='#007bff', cornerRadiusEnd=5).encode(
                x=alt.X('VALOR:Q', title='Valor Total', axis=alt.Axis(format=',.2f')),
                y=alt.Y('CLIENTE:N', sort='-x', title=None),
                tooltip=[alt.Tooltip('CLIENTE:N'), alt.Tooltip('VALOR:Q', format=',.2f', title='Valor (R$)')]
            ).properties(height=alt.Step(40)) 
            st.altair_chart(chart_cli, use_container_width=True)

        with g2:
            st.write("**Faturamento por Hora**")
            df_resumo['HORA_SIMPLES'] = df_resumo['HORA'].str[:2]
            fatur_hora = df_resumo.groupby('HORA_SIMPLES')['VALOR'].sum().reset_index()
            chart_hora = alt.Chart(fatur_hora).mark_area(
                line={'color':'#28a745'},
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='white', offset=0),
                           alt.GradientStop(color='#28a745', offset=1)],
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(
                x=alt.X('HORA_SIMPLES:N', title='Hora do Dia'),
                y=alt.Y('VALOR:Q', title='Total (R$)', axis=alt.Axis(format=',.2f')),
                tooltip=[alt.Tooltip('HORA_SIMPLES:N', title='Hora'), alt.Tooltip('VALOR:Q', format=',.2f', title='Total')]
            ).properties(height=200) # Altura fixa menor para ficar elegante
            st.altair_chart(chart_hora, use_container_width=True)

        # --- TABELA DE DADOS (Busca removida) ---
        st.write("---")
        df_disp = df_resumo[['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']].copy()
        df_disp['VALOR'] = df_disp['VALOR'].apply(formatar_moeda)
        
        selecao = st.dataframe(
            df_disp, use_container_width=True, hide_index=True, 
            on_select="rerun", selection_mode="single-row",
            column_config={"CLIENTE": st.column_config.TextColumn("Cliente", width=600)}
        )

        # --- DETALHE ---
        if selecao.get("selection", {}).get("rows"):
            idx = selecao["selection"]["rows"][0]
            num_ped = df_resumo.iloc[idx]['PEDIDO']
            df_itens = df_filtrado[df_filtrado.iloc[:, 10] == num_ped]
            
            st.write("###")
            c_det1, c_det2, c_det3 = st.columns(3)
            with c_det1: st.info(f"**Cliente:** {df_itens.iloc[0, 5]}\n\n**Pedido:** {num_ped}")
            with c_det2: st.warning(f"**Coligação:** {df_itens.iloc[0, 6]}\n\n**NF-e:** {df_itens.iloc[0, 11]}")
            with c_det3: st.success(f"**Valor:** {formatar_moeda(df_itens['VALOR_NUM'].sum())}\n\n**Peso:** {df_itens['PESO_NUM'].sum():,.2f} kg".replace(".", ","))

            # Tabela de itens com nomes de colunas limpos
            df_itens_det = df_itens.iloc[:, [13, 15, 7, 19, 20, 22]].copy()
            df_itens_det.columns = ['CÓDIGO', 'PRODUTO', 'FABRICANTE', 'CX', 'UN', 'VALOR']
            df_itens_det['VALOR'] = df_itens_det['VALOR'].apply(limpar_para_numero).apply(formatar_moeda)
            
            st.dataframe(df_itens_det, hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum dado encontrado para os filtros selecionados.")
