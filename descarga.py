import streamlit as st
import pandas as pd
from datetime import date, timedelta
import re
import io
from fpdf import FPDF
import altair as alt

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="CCN BI - Performance Turbo", page_icon="📈")

# --- CONEXÃO SQL ---
# Certifique-se de que o segredo 'dialect' seja 'mssql+pymssql'
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
    .stDownloadButton button { border-radius: 8px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- CLASSE PDF ---
class PDF(FPDF):
    def header(self):
        try: self.image('sem_fundo.png', 10, 8, 33)
        except: pass
        self.set_font('Arial', 'B', 14)
        self.cell(200, 10, 'RELATORIO DE CARGA OPERACIONAL', 0, 0, 'C')
        self.ln(20)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()} | CCN BI', 0, 0, 'C')

# --- FUNÇÕES DE APOIO ---
def formatar_moeda(valor):
    try: return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "R$ 0,00"

def gerar_pdf_completo(df, vendedor, periodo_str, faturamento, peso, qtd):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(190, 10, f" Vendedor: {vendedor} | Periodo: {periodo_str}", 1, 1, 'L', fill=True)
    pdf.ln(5)
    
    # Resumo
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(63, 10, "Faturamento", 1, 0, 'C'); pdf.cell(63, 10, "Peso", 1, 0, 'C'); pdf.cell(64, 10, "Pedidos", 1, 1, 'C')
    pdf.set_font('Arial', '', 10)
    pdf.cell(63, 10, faturamento, 1, 0, 'C')
    pdf.cell(63, 10, f"{peso:,.2f} kg".replace(".", ","), 1, 0, 'C')
    pdf.cell(64, 10, str(qtd), 1, 1, 'C')
    pdf.ln(10)

    # Tabela
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
    
    return pdf.output(dest='S').encode('latin-1')

# --- CARREGAMENTO DE DADOS (SQL TURBO) ---

@st.cache_data(ttl=3600)
def load_vendedores():
    query = """
    SELECT DISTINCT v.cd_vend AS [Cod], v.nome AS [Vendedor] 
    FROM vendedor v
    INNER JOIN categ c ON c.categ = v.categ
    WHERE v.ativo = 1 AND v.categ IN ('11','13','14','23','28','31','25','12','18','7')
    ORDER BY v.nome
    """
    return conn.query(query)

@st.cache_data(ttl=300)
def load_faturamento_turbo(data_ini, data_fim, cod_vend):
    # Otimização: Filtrar primeiro os pedidos, depois fazer Joins e Subqueries
    query = f"""
    WITH PedidosBase AS (
        SELECT p.nu_ped, p.cd_clien, p.cd_emp, p.dt_cad, p.valor_tot
        FROM ped_vda p
        WHERE p.cd_emp = 2 
          AND p.dt_cad BETWEEN '{data_ini}' AND '{data_fim}'
          AND p.cd_vend = '{cod_vend}'
    ),
    Horarios AS (
        SELECT nu_ped, MIN(dt_criacao) as Horario_Descarga
        FROM VI_evento
        WHERE cd_fila = 'CAPV' AND nu_ped IN (SELECT nu_ped FROM PedidosBase)
        GROUP BY nu_ped
    )
    SELECT 
        pb.cd_clien AS [Cod_Cliente], cl.nome AS [Cliente], co.descricao AS [Coligacao],
        h.Horario_Descarga, pb.nu_ped AS [Pedido], ISNULL(CAST(n.nu_nf_emp_fat AS VARCHAR), 'SEM NOTA') AS [NFe],
        prod.cd_prod AS [Cod_Prod], prod.descricao AS [Produto], f.descricao AS [Fabricante],
        it.vl_venda AS [Valor_Total_Item], (it.qtde * prod.peso_liq) AS [Peso_Total_Real],
        it.qtde, prod.qtde_unid_cmp
    FROM PedidosBase pb
    INNER JOIN it_pedv it ON it.nu_ped = pb.nu_ped AND it.cd_emp = pb.cd_emp
    INNER JOIN cliente cl ON cl.cd_clien = pb.cd_clien
    INNER JOIN produto prod ON prod.cd_prod = it.cd_prod
    INNER JOIN fabric f ON f.cd_fabric = prod.cd_fabric
    LEFT JOIN coligacao co ON co.cd_coligacao = cl.cd_coligacao
    LEFT JOIN Horarios h ON h.nu_ped = pb.nu_ped
    LEFT JOIN nota n ON n.nu_ped = pb.nu_ped AND n.cd_emp = pb.cd_emp
    WHERE it.situacao IN ('FA', 'AB')
    """
    return conn.query(query)

# --- LOGICA DA INTERFACE ---

df_vends = load_vendedores()

with st.sidebar:
    try: st.image("sem_fundo.png", use_container_width=True)
    except: pass
    st.header("Filtros de Período")
    
    # Range de datas padrão para Março de 2026
    periodo = st.date_input(
        "Selecione o Intervalo",
        value=(date(2026, 3, 1), date(2026, 3, 31)),
        format="DD/MM/YYYY"
    )
    
    nome_vendedor = st.selectbox("👤 Vendedor", df_vends['Vendedor'].unique())
    cod_vendedor = df_vends[df_vends['Vendedor'] == nome_vendedor]['Cod'].iloc[0]
    
    st.divider()
    st.caption("v6.2 - CCN Turbo Engine")

# Execução da busca
if isinstance(periodo, tuple) and len(periodo) == 2:
    d_ini, d_fim = periodo
    str_ini, str_fim = d_ini.strftime('%Y%m%d'), d_fim.strftime('%Y%m%d')
    
    with st.spinner('Processando dados no servidor...'):
        df_raw = load_faturamento_turbo(str_ini, str_fim, cod_vendedor)

    if not df_raw.empty:
        # Processamento de datas e horas
        df_raw['Horario_Descarga'] = pd.to_datetime(df_raw['Horario_Descarga'])
        df_raw['HORA_STR'] = df_raw['Horario_Descarga'].dt.strftime('%H:%M')
        
        # Agrupamento por Pedido (Resumo)
        df_resumo = df_raw.groupby('Pedido').agg({
            'Cod_Cliente': 'first', 'Cliente': 'first', 'Valor_Total_Item': 'sum',
            'NFe': 'first', 'HORA_STR': 'first', 'Coligacao': 'first'
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA', 'COLIGACAO']

        # Cabeçalho e Botões
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            st.title("🚀 Performance de Vendas")
            st.write(f"Vendedor: **{nome_vendedor}** | **{d_ini.strftime('%d/%m')}** a **{d_fim.strftime('%d/%m/%Y')}**")
        
        fat_tot = df_resumo['VALOR'].sum()
        peso_tot = df_raw['Peso_Total_Real'].sum()

        with c2:
            st.write("##")
            out_ex = io.BytesIO()
            df_resumo.to_excel(out_ex, index=False)
            st.download_button("📥 Excel", out_ex.getvalue(), f"Vendas_{nome_vendedor}.xlsx", use_container_width=True)
        with c3:
            st.write("##")
            df_pdf = df_resumo.copy()
            df_pdf['VALOR'] = df_pdf['VALOR'].apply(formatar_moeda)
            pdf_bytes = gerar_pdf_completo(df_pdf, nome_vendedor, f"{d_ini.strftime('%d/%m')}-{d_fim.strftime('%d/%m')}", formatar_moeda(fat_tot), peso_tot, len(df_resumo))
            st.download_button("📄 PDF", pdf_bytes, f"Relatorio_{nome_vendedor}.pdf", use_container_width=True)

        # Métricas KPIs
        st.divider()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Faturamento", formatar_moeda(fat_tot))
        k2.metric("Peso Total", f"{peso_tot:,.2f} kg")
        k3.metric("Pedidos", len(df_resumo))
        k4.metric("Ticket Médio", formatar_moeda(fat_tot/len(df_resumo)) if len(df_resumo) > 0 else 0)

        # Gráficos
        st.write("### 📊 Evolução Diária")
        df_raw['Data'] = df_raw['Horario_Descarga'].dt.date
        vendas_dia = df_raw.groupby('Data')['Valor_Total_Item'].sum().reset_index()
        chart_dia = alt.Chart(vendas_dia).mark_line(point=True, color='#28a745').encode(
            x=alt.X('Data:T', title='Dia'),
            y=alt.Y('Valor_Total_Item:Q', title='Total (R$)'),
            tooltip=['Data', 'Valor_Total_Item']
        ).properties(height=250)
        st.altair_chart(chart_dia, use_container_width=True)

        # Tabela e Detalhes
        st.write("### 📝 Lista de Pedidos")
        df_disp = df_resumo.copy()
        df_disp['VALOR'] = df_disp['VALOR'].apply(formatar_moeda)
        
        selected = st.dataframe(
            df_disp, 
            use_container_width=True, 
            hide_index=True, 
            on_select="rerun", 
            selection_mode="single-row"
        )

        # Detalhe do Pedido Selecionado
        if selected.get("selection", {}).get("rows"):
            idx = selected["selection"]["rows"][0]
            ped_id = df_resumo.iloc[idx]['PEDIDO']
            df_it = df_raw[df_raw['Pedido'] == ped_id].copy()
            
            st.info(f"📦 Itens do Pedido: **{ped_id}** | Cliente: **{df_it.iloc[0]['Cliente']}**")
            df_it_det = df_it[['Cod_Prod', 'Produto', 'Fabricante', 'Valor_Total_Item']].copy()
            df_it_det.columns = ['CÓDIGO', 'PRODUTO', 'FABRICANTE', 'VALOR']
            df_it_det['VALOR'] = df_it_det['VALOR'].apply(formatar_moeda)
            st.dataframe(df_it_det, hide_index=True, use_container_width=True)

    else:
        st.info(f"Nenhum dado encontrado para {nome_vendedor} no período selecionado.")
else:
    st.warning("Selecione o início e o fim do período no calendário lateral.")
