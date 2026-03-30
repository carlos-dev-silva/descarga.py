import streamlit as st
import pandas as pd
from datetime import date
import re
import io
from fpdf import FPDF
import altair as alt

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="CCN - Performance SQL", page_icon="📈")

# --- CONEXÃO SQL ---
conn = st.connection("sql")

# --- ESTILIZAÇÃO CSS ---
st.markdown("""
    <style>
    div[data-testid="stMetric"] { background-color: #ffffff; border: 1px solid #e0e0e0; padding: 15px 20px; border-radius: 12px; }
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

# --- FUNÇÕES DE APOIO ---
def formatar_moeda(valor):
    try: return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "R$ 0,00"

# --- CARREGAMENTO DE DADOS OTIMIZADO ---

@st.cache_data(ttl=3600)
def load_vendedores():
    query = "SELECT DISTINCT cd_vend AS [Cod_Vendedor], nome AS [Vendedor] FROM vendedor WHERE ativo = 1 ORDER BY nome"
    return conn.query(query)

@st.cache_data(ttl=300) # Cache curto para dados de vendas (5 min)
def load_faturamento_range(data_ini_str, data_fim_str, cod_vend):
    """
    Busca dados filtrando diretamente no SQL por data no formato YYYYMMDD
    """
    query = f"""
    SELECT
        cl.cd_clien AS [Cod_Cliente], 
        v.nome AS [Vendedor],
        cl.nome AS [Cliente], 
        (SELECT co.descricao FROM coligacao co WHERE co.cd_coligacao = cl.cd_coligacao) AS [Coligacao],
        (SELECT MIN(ev.dt_criacao) FROM VI_evento ev WHERE ev.nu_ped = p.nu_ped AND ev.cd_fila = 'CAPV') AS [Horario_Descarga],
        p.nu_ped AS [Pedido], 
        ISNULL(CAST(n.nu_nf_emp_fat AS VARCHAR), 'SEM NOTA') AS [NFe],
        prod.descricao AS [Produto], 
        it.vl_venda AS [Valor_Total_Item],
        ((it.qtde * prod.peso_liq)) AS [Peso_Total_Real]
    FROM ped_vda p
    INNER JOIN it_pedv it ON it.nu_ped = p.nu_ped AND it.cd_emp = p.cd_emp
    INNER JOIN cliente cl ON cl.cd_clien = p.cd_clien
    INNER JOIN vendedor v ON v.cd_vend = p.cd_vend
    INNER JOIN produto prod ON prod.cd_prod = it.cd_prod
    LEFT JOIN nota n ON n.nu_ped = p.nu_ped AND n.cd_emp = p.cd_emp
    WHERE p.cd_emp = 2 
      AND p.dt_cad BETWEEN '{data_ini_str}' AND '{data_fim_str}'
      AND v.cd_vend = '{cod_vend}'
      AND it.situacao IN ('FA', 'AB')
    """
    return conn.query(query)

# --- INTERFACE ---

df_vendedores = load_vendedores()

with st.sidebar:
    try: st.image("sem_fundo.png", use_container_width=True)
    except: pass
    st.header("Filtros de Busca")
    
    # Seletor de Datas
    hoje = date.today()
    periodo = st.date_input(
        "Selecione o Intervalo",
        value=(date(2026, 3, 1), date(2026, 3, 31)), # Padrão Março/2026
        format="DD/MM/YYYY"
    )
    
    nome_vend = st.selectbox("👤 Vendedor", df_vendedores['Vendedor'].unique())
    cod_vend_sel = df_vendedores[df_vendedores['Vendedor'] == nome_vend]['Cod_Vendedor'].iloc[0]
    
    st.divider()
    st.caption("v6.0 - SQL Otimizado")

# Processamento do Intervalo
if isinstance(periodo, tuple) and len(periodo) == 2:
    d_ini, d_fim = periodo
    
    # CONVERSÃO PARA FORMATO SQL (YYYYMMDD) - Isso garante velocidade!
    str_ini = d_ini.strftime('%Y%m%d')
    str_fim = d_fim.strftime('%Y%m%d')
    
    with st.spinner(f'Buscando dados de {d_ini.strftime("%d/%m")} até {d_fim.strftime("%d/%m")}...'):
        df_filtrado = load_faturamento_range(str_ini, str_fim, cod_vend_sel)

    if not df_filtrado.empty:
        # Tratamento de dados no Python após o SQL filtrar
        df_filtrado['Horario_Descarga'] = pd.to_datetime(df_filtrado['Horario_Descarga'])
        df_filtrado['HORA'] = df_filtrado['Horario_Descarga'].dt.strftime('%H:%M')
        
        # Resumo por Pedido
        df_resumo = df_filtrado.groupby('Pedido').agg({
            'Cod_Cliente': 'first', 'Cliente': 'first', 'Valor_Total_Item': 'sum', 
            'NFe': 'first', 'HORA': 'first', 'Coligacao': 'first'
        }).reset_index()
        df_resumo.columns = ['PEDIDO', 'COD_CLI', 'CLIENTE', 'VALOR', 'NFE', 'HORA', 'COLIGACAO']

        # Cabeçalho e Métricas
        st.title("🚀 Performance de Vendas")
        st.write(f"Período: **{d_ini.strftime('%d/%m/%Y')}** a **{d_fim.strftime('%d/%m/%Y')}**")
        
        k1, k2, k3 = st.columns(3)
        fat_tot = df_resumo['VALOR'].sum()
        k1.metric("Faturamento Total", formatar_moeda(fat_tot))
        k2.metric("Total Pedidos", len(df_resumo))
        k3.metric("Peso Total (kg)", f"{df_filtrado['Peso_Total_Real'].sum():,.2f}")

        # Gráfico de Faturamento por Dia (Novo para períodos longos)
        st.write("### 📊 Evolução das Vendas")
        df_filtrado['Data'] = df_filtrado['Horario_Descarga'].dt.date
        vendas_dia = df_filtrado.groupby('Data')['Valor_Total_Item'].sum().reset_index()
        chart = alt.Chart(vendas_dia).mark_line(point=True, color='#28a745').encode(
            x='Data:T',
            y='Valor_Total_Item:Q',
            tooltip=['Data', 'Valor_Total_Item']
        ).properties(height=250)
        st.altair_chart(chart, use_container_width=True)

        # Tabela
        st.write("---")
        df_disp = df_resumo.copy()
        df_disp['VALOR'] = df_disp['VALOR'].apply(formatar_moeda)
        st.dataframe(df_disp, use_container_width=True, hide_index=True)

    else:
        st.info("Nenhum dado encontrado para este vendedor no período selecionado.")
else:
    st.warning("Selecione a data inicial e final no calendário lateral.")
