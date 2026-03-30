import streamlit as st
import pandas as pd
from datetime import date, timedelta
import re
import io
from fpdf import FPDF
import altair as alt

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="CCN - Business Intelligence", page_icon="📈")

# --- CONEXÃO SQL ---
conn = st.connection("sql")

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
    div[data-testid="stMetricLabel"] { font-size: 14px !important; color: #666666 !important; font-weight: bold; }
    .stDownloadButton button { border-radius: 8px !important; border: 1px solid #d1d1d1 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- CLASSE PDF PROFISSIONAL ---
class PDF(FPDF):
    def header(self):
        try: self.image('sem_fundo.png', 10, 8, 33)
        except: pass
        self.set_font('Arial', 'B', 14)
        self.cell(80)
        self.cell(30, 10, 'RELATORIO DE CARGA OPERACIONAL', 0, 0, 'C')
        self.ln(20)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()} | CCN BI', 0, 0, 'C')

# --- FUNÇÕES DE APOIO ---
def formatar_moeda(valor):
    try: return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "R$ 0,00"

def gerar_pdf_completo(df, vendedor, data_doc, faturamento, peso, qtd):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(190, 10, f" Vendedor: {vendedor} | Periodo: {data_doc}", 1, 1, 'L', fill=True)
    pdf.ln(5)
    
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(63, 10, "Faturamento", 1, 0, 'C'); pdf.cell(63, 10, "Peso", 1, 0, 'C'); pdf.cell(64, 10, "Pedidos", 1, 1, 'C')
    pdf.set_font('Arial', '', 10)
    pdf.cell(63, 10, faturamento, 1, 0, 'C')
    pdf.cell(63, 10, f"{peso:,.2f} kg".replace(".", ","), 1, 0, 'C')
    pdf.cell(64, 10, str(qtd), 1, 1, 'C')
    pdf.ln(10)

    pdf.set_fill_color(0, 51, 102); pdf.set_text_color(255, 255, 255); pdf.set_font('Arial', 'B', 9)
    cols = [("PEDIDO", 20), ("COD", 20), ("CLIENTE", 90), ("VALOR", 30), ("HORA", 30)]
    for txt, w in cols: pdf.cell(w, 10, txt, 1, 0, 'C', fill=True)
    pdf.ln(); pdf.set_text_color(0, 0, 0); pdf.set_font('Arial', '', 8)

    for i, row in df.iterrows():
        fill = i % 2 == 0
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(20, 8, str(row['PEDIDO']), 1, 0, 'C', fill=fill)
        pdf.cell(20, 8, str(row['COD_CLI']), 1, 0, 'C', fill=fill)
        pdf.cell(90, 8, str(row['CLIENTE'])[:50], 1, 0, 'L', fill=fill)
        pdf.cell(30, 8, str(row['VALOR']), 1, 0, 'C', fill=fill)
        pdf.cell(30, 8, str(row['HORA']), 1, 1, 'C', fill=fill)
    
    res = pdf.output(dest='S')
    return res.encode('latin-1') if isinstance(res, str) else res

# --- CARREGAMENTO DE DADOS (SQL) ---

@st.cache_data(ttl=3600)
def load_vendedores():
    query = """
    SELECT DISTINCT vend.cd_vend AS [Cod_Vendedor], vend.nome AS [Vendedor]
    FROM vendedor vend
    INNER JOIN categ ct ON ct.categ = vend.categ
    WHERE vend.ativo = 1 AND vend.categ IN ('11','13','14','23','28','31','25','12','18','7')
    ORDER BY vend.nome
    """
    return conn.query(query)

@st.cache_data(ttl=600)
def load_faturamento(dt_inicio, dt_fim):
    query = f"""
    SELECT
        cl.cd_clien AS [Cod_Cliente], v.cd_vend AS [Cod_Vendedor], v.nome AS [Vendedor],
        cl.nome AS [Cliente], (SELECT co.descricao FROM coligacao co WHERE co.cd_coligacao = cl.cd_coligacao) AS [Coligacao],
        f.descricao AS [Fabricante],
        (SELECT MIN(ev.dt_criacao) FROM VI_evento ev WHERE ev.nu_ped = p.nu_ped AND ev.cd_fila = 'CAPV') AS [Horario_Descarga],
        p.dt_cad AS [Dt_Pedido], p.nu_ped AS [Pedido], ISNULL(CAST(n.nu_nf_emp_fat AS VARCHAR), 'SEM NOTA') AS [NFe],
        prod.cd_prod AS [Cod_Prod], prod.descricao AS [Produto], it.vl_venda AS [Valor_Total_Item],
        ((FLOOR(it.qtde / NULLIF(prod.qtde_unid_cmp, 0)) * (prod.qtde_unid_cmp * prod.peso_liq)) + 
        ((CAST(CAST(it.qtde AS INT) % CAST(NULLIF(prod.qtde_unid_cmp, 0) AS INT) AS INT)) * prod.peso_liq)) AS [Peso_Total_Real],
        it.qtde AS [Qtd_Total], it.preco_unit AS [Preco_Unit], 
        FLOOR(it.qtde / NULLIF(prod.qtde_unid_cmp, 0)) AS [CX],
        CAST(CAST(it.qtde AS INT) % CAST(NULLIF(prod.qtde_unid_cmp, 0) AS INT) AS INT) AS [UN]
    FROM ped_vda p
    INNER JOIN it_pedv it ON it.nu_ped = p.nu_ped AND it.cd_emp = p.cd_emp
    INNER JOIN cliente cl ON cl.cd_clien = p.cd_clien
    INNER JOIN vendedor v ON v.cd_vend = p.cd_vend
    INNER JOIN produto prod ON prod.cd_prod = it.cd_prod
    INNER JOIN fabric f ON f.cd_fabric = prod.cd_fabric
    LEFT JOIN nota n ON n.nu_ped = p.nu_ped AND n.cd_emp = p.cd_emp
    WHERE p.cd_emp = 2 
      AND p.dt_cad BETWEEN '{dt_inicio}' AND '{dt_fim}'
      AND it.situacao IN ('FA', 'AB')
    """
    df = conn.query(query)
    if not df.empty:
        df['DATA_FILTRO'] = pd.to_datetime(df['Horario_Descarga']).dt.date
        df['HORA_STR'] = pd.to_datetime(df['Horario_Descarga']).dt.strftime('%H:%M')
    return df

# --- INTERFACE PRINCIPAL ---

df_vendedores = load_vendedores()

if not df_vendedores.empty:
    with st.sidebar:
        try: st.image("sem_fundo.png", use_container_width=True)
        except: pass
        st.write("---")
        
        # SELETOR DE RANGE DE DATAS
        hoje = date.today()
        periodo = st.date_input("🗓️ Período da Descarga", value=(hoje, hoje), format="DD/MM/YYYY")
        
        vendedor_lista = sorted(df_vendedores['Vendedor'].unique())
        nome_vend = st.selectbox("👤 Vendedor", vendedor_lista)
        cod_vend_sel = df_vendedores[df_vendedores['Vendedor'] == nome_vend]['Cod_Vendedor'].iloc[0]
        
        st.divider(); st.caption("v5.2 - CCN Intelligence Range")

    # Verifica se o intervalo foi selecionado corretamente
    if isinstance(periodo, tuple) and len(periodo) == 2:
        data_ini, data_fim = periodo
        
        # SQL busca com margem para garantir descarga
        df_raw = load_faturamento(data_ini - timedelta(days=3), data_fim)

        if not df_raw.empty:
            # Filtro no Pandas por Range
            mask = (
                (df_raw['DATA_FILTRO'] >= data_ini) & 
                (df_raw['DATA_FILTRO'] <= data_fim) & 
                (df_raw['Cod_Vendedor'].astype(str).str.strip() == str(cod_vend_sel).strip())
            )
            df_filtrado = df_raw[mask].copy()

            if not df_filtrado.empty:
                df_resumo = df_filtrado.groupby('Pedido').agg({
                    'Cod_Cliente': 'first', 'Cliente': 'first', 'Valor_Total_Item': 'sum', 
                    'NFe': 'first', 'HORA_STR': 'first', 'Coligacao': 'first'
                }).reset_index()
                df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA', 'COLIGACAO']

                # --- EXIBIÇÃO ---
                h1, h2, h3 = st.columns([4, 1, 1])
                with h1:
                    st.title("🚀 Performance de Vendas")
                    st.write(f"Vendedor: **{nome_vend}** | Período: **{data_ini.strftime('%d/%m')}** até **{data_fim.strftime('%d/%m/%Y')}**")
                
                fat_tot = df_resumo['VALOR'].sum()
                peso_tot = df_filtrado['Peso_Total_Real'].sum()

                with h2:
                    st.write("##")
                    out_ex = io.BytesIO()
                    df_resumo.to_excel(out_ex, index=False)
                    st.download_button("📥 Excel", out_ex.getvalue(), f"Resumo_{nome_vend}.xlsx", use_container_width=True)
                with h3:
                    st.write("##")
                    df_pdf_data = df_resumo.copy()
                    df_pdf_data['VALOR'] = df_pdf_data['VALOR'].apply(formatar_moeda)
                    data_str = f"{data_ini.strftime('%d/%m')} - {data_fim.strftime('%d/%m')}"
                    btn_pdf = gerar_pdf_completo(df_pdf_data, nome_vend, data_str, formatar_moeda(fat_tot), peso_tot, len(df_resumo))
                    st.download_button("📄 PDF", btn_pdf, f"Relatorio_{nome_vend}.pdf", use_container_width=True)

                # KPIs
                st.write("---")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Faturamento Total", formatar_moeda(fat_tot))
                k2.metric("Peso Total", f"{peso_tot:,.2f} kg".replace(".", ","))
                k3.metric("Qtd Pedidos", len(df_resumo))
                k4.metric("Ticket Médio", formatar_moeda(fat_tot/len(df_resumo)) if len(df_resumo) > 0 else 0)

                # Gráficos
                st.write("### 📊 Análise Visual")
                g1, g2 = st.columns(2)
                with g1:
                    st.write("**Top 5 Clientes do Período**")
                    top_cli = df_resumo.nlargest(5, 'VALOR').copy()
                    chart_cli = alt.Chart(top_cli).mark_bar(color='#007bff', cornerRadiusEnd=5).encode(
                        x=alt.X('VALOR:Q', title='Total (R$)'),
                        y=alt.Y('CLIENTE:N', sort='-x', title=None),
                        tooltip=['CLIENTE', 'VALOR']
                    ).properties(height=200)
                    st.altair_chart(chart_cli, use_container_width=True)
                with g2:
                    st.write("**Concentração de Vendas por Hora**")
                    df_resumo['H_INDEX'] = df_resumo['HORA'].str[:2] + ":00h"
                    fatur_h = df_resumo.groupby('H_INDEX')['VALOR'].sum().reset_index()
                    chart_h = alt.Chart(fatur_h).mark_area(line={'color':'#28a745'}, color=alt.Gradient(gradient='linear', stops=[alt.GradientStop(color='white', offset=0), alt.GradientStop(color='#28a745', offset=1)], x1=1, x2=1, y1=1, y2=0)).encode(
                        x=alt.X('H_INDEX:N', title='Hora'),
                        y=alt.Y('VALOR:Q', title='Total (R$)')
                    ).properties(height=200)
                    st.altair_chart(chart_h, use_container_width=True)

                # Tabela Principal
                st.write("---")
                df_disp = df_resumo[['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA']].copy()
                df_disp['VALOR'] = df_disp['VALOR'].apply(formatar_moeda)
                sel = st.dataframe(df_disp, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

                if sel.get("selection", {}).get("rows"):
                    idx = sel["selection"]["rows"][0]
                    num_ped = df_resumo.iloc[idx]['PEDIDO']
                    df_it = df_filtrado[df_filtrado['Pedido'] == num_ped]
                    st.write("### 📦 Detalhes do Pedido Selecionado")
                    st.info(f"**Cliente:** {df_it.iloc[0]['Cliente']} | **Pedido:** {num_ped}")
                    df_it_det = df_it[['Cod_Prod', 'Produto', 'Fabricante', 'CX', 'UN', 'Valor_Total_Item']].copy()
                    df_it_det.columns = ['CÓDIGO', 'PRODUTO', 'FABRICANTE', 'CX', 'UN', 'VALOR']
                    df_it_det['VALOR'] = df_it_det['VALOR'].apply(formatar_moeda)
                    st.dataframe(df_it_det, hide_index=True, use_container_width=True)
            else:
                st.info(f"Nenhuma carga descarregada para {nome_vend} entre {data_ini.strftime('%d/%m')} e {data_fim.strftime('%d/%m')}.")
        else:
            st.warning("Sem dados encontrados no banco de dados.")
    else:
        st.info("Por favor, selecione as duas datas (Início e Fim) no calendário lateral.")
else:
    st.error("Erro de Conexão: Não foi possível carregar vendedores. Verifique o IP e a porta 1433.")
