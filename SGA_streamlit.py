import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import datetime
import numpy as np
import os

# ==============================================================================
# CONFIGURACIÓN GENERAL
# ==============================================================================
st.set_page_config(
    page_title="Dashboard SGA Control",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- NOMBRES DE ARCHIVOS ---
DATA_FILENAME = "data_sga_source.xlsx" 
BUDGET_FILENAME = "2025 10 13 - SGA MOD - V31 - send 1.xlsx" 

# --- COLORES ---
COLOR_TOTALS = '#003366'    
COLOR_BARS_REAL = '#3399FF' 
COLOR_GOOD = '#009966'      
COLOR_BAD = '#CC0000'       
COLOR_NEUTRAL = 'rgba(128, 128, 128, 0.5)'
MOM_COLOR_PREV = '#CC0000'
MOM_COLOR_CURR = '#003366'
MOM_COLOR_BUD = '#F4D03F'

# ==============================================================================
# 1. FUNCIONES AUXILIARES
# ==============================================================================
def normalizar_denom3(texto):
    if pd.isna(texto): return "OTROS"
    t = str(texto).upper().strip()
    if any(x in t for x in ['SALAR', 'WAGE', 'SUELDO', 'REMUNERACION', 'PAYROLL', 'PERSONAL']): return "SALARY"
    if any(x in t for x in ['TRAVEL', 'VIAJE', 'HOTEL', 'FLIGHT', 'LODGING']): return "TRAVEL"
    if any(x in t for x in ['RE-INVOICE', 'REINVOICE', 'INTERCOMPANY']): return "RE-INVOICED"
    if any(x in t for x in ['FEE', 'CONSULT', 'HONORARIO', 'LEGAL']): return "FEES"
    if any(x in t for x in ['RENT', 'ARRIENDO', 'LEASE']): return "RENTAL"
    if any(x in t for x in ['DEPRECIATION', 'AMORTIZATION']): return "DEPRECIATION"
    if any(x in t for x in ['TELECOM', 'MAIL']): return "TELECOM/MAIL"
    if any(x in t for x in ['SUPPLIE', 'SUPLIE']): return "SUPPLIES"
    if any(x in t for x in ['ENERGY']): return "ENERGY"
    if any(x in t for x in ['TAX', 'INSURANCE']): return "TAX/INSURANCE"
    if any(x in t for x in ['OTHER']): return "OTHER"
    return t

# ==============================================================================
# 2. CARGA DE DATOS
# ==============================================================================
@st.cache_data
def load_data_from_excel(filename):
    if not os.path.exists(filename):
        return None, f"⚠️ No se encuentra el archivo: {filename}"

    try:
        df = pd.read_excel(filename, sheet_name='BD_EERR')
        df['Fecha_Str'] = df['Year/month'].astype(str).str.replace('.', '/', regex=False)
        df['Fecha'] = pd.to_datetime(df['Fecha_Str'], errors='coerce')
        df['Fecha'] = df['Fecha'].apply(lambda x: x.replace(day=1) if pd.notnull(x) else x)
        df = df.dropna(subset=['Fecha'])
        df['Concepto_Norm'] = df['Denom3'].apply(normalizar_denom3)
        df['Gasto_Real'] = df['Valor'] * 1 
        df = df.sort_values('Fecha')
        return df, "Datos cargados correctamente."
    except Exception as e:
        return None, f"Error leyendo Excel de Datos: {e}"

@st.cache_data
def load_budget_excel(filename):
    if not os.path.exists(filename):
        return pd.DataFrame(columns=['Desc_Ceco', 'Concepto_Norm', 'Budget_Anual'])
    try:
        df_ex = pd.read_excel(filename, header=5)
        col_ceco_name = df_ex.columns[1]
        df_ex = df_ex.dropna(subset=[col_ceco_name])
        if len(df_ex.columns) < 3: return pd.DataFrame()

        all_cols = df_ex.columns[2:]
        cols_conceptos = [c for c in all_cols if str(c).lower().strip() != 'total general' and not str(c).startswith('Unnamed')]
        
        df_melt = df_ex.melt(id_vars=[col_ceco_name], value_vars=cols_conceptos, var_name='Concepto_Raw', value_name='Budget_Anual')
        df_melt = df_melt.rename(columns={col_ceco_name: 'Desc_Ceco'})
        
        df_melt['Budget_Anual'] = pd.to_numeric(df_melt['Budget_Anual'], errors='coerce').fillna(0) * 1000
        df_melt['Desc_Ceco'] = df_melt['Desc_Ceco'].astype(str).str.upper().str.strip()
        df_melt = df_melt[~df_melt['Desc_Ceco'].isin(['NAN', 'NONE', ''])]
        df_melt['Concepto_Norm'] = df_melt['Concepto_Raw'].apply(normalizar_denom3)
        
        return df_melt.groupby(['Desc_Ceco', 'Concepto_Norm'])['Budget_Anual'].sum().reset_index()
    except Exception as e:
        st.error(f"Error leyendo Budget: {e}")
        return pd.DataFrame(columns=['Desc_Ceco', 'Concepto_Norm', 'Budget_Anual'])

# ==============================================================================
# 3. GRÁFICOS
# ==============================================================================
def plot_waterfall_generic(labels, wf_values, wf_measures, bar_values, title, is_drilldown=False, simple_bar_mode=False, bar_custom_text=None, val_prior_year=None, label_prior_year="Año Ant"):
    fig = go.Figure()

    if val_prior_year is not None:
        labels.append(label_prior_year)
        wf_values.append(val_prior_year)
        wf_measures.append("absolute")
        bar_values.append(val_prior_year)
        if bar_custom_text: bar_custom_text.append(f"${val_prior_year:,.0f}")

    bg_colors = [MOM_COLOR_BUD if i==0 else (MOM_COLOR_PREV if m=="absolute" and i==len(wf_measures)-1 and val_prior_year else (COLOR_TOTALS if m=="total" else COLOR_BARS_REAL)) for i, m in enumerate(wf_measures)]
    
    text_list_bar = bar_custom_text if bar_custom_text else [f"${v:,.0f}" if v!=0 else "" for v in bar_values]
    if not bar_custom_text and val_prior_year: text_list_bar[-1] = f"${val_prior_year:,.0f}"

    wf_text = ["" if m in ["absolute", "total"] else f"${v:,.0f}" for i, (m, v) in enumerate(zip(wf_measures, wf_values))]

    fig.add_trace(go.Bar(name="Ref", x=labels, y=bar_values, text=text_list_bar, textposition='outside', marker_color=bg_colors))
    
    if not simple_bar_mode:
        fig.add_trace(go.Waterfall(name="Var", orientation="v", measure=wf_measures, x=labels, y=wf_values, text=wf_text, textposition="outside", connector={"line": {"color": COLOR_NEUTRAL}}, increasing={"marker": {"color": COLOR_BAD}}, decreasing={"marker": {"color": COLOR_GOOD}}, totals={"marker": {"color": "rgba(0,0,0,0)"}}))

    fig.update_layout(title=title, yaxis_title="$", template="plotly_white", barmode='overlay', height=600 if is_drilldown else 700, showlegend=False, margin=dict(t=80))
    return fig

def plot_mom_evolution(df_all, selected_year, total_monthly_budget):
    prior = selected_year - 1
    df_curr, df_prev = df_all[df_all['Fecha'].dt.year == selected_year], df_all[df_all['Fecha'].dt.year == prior]
    vals_curr = [df_curr[df_curr['Fecha'].dt.month == m]['Gasto_Real'].sum() for m in range(1,13)]
    vals_prev = [df_prev[df_prev['Fecha'].dt.month == m]['Gasto_Real'].sum() for m in range(1,13)]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"], y=vals_prev, name=f"{prior}", line=dict(color=MOM_COLOR_PREV, dash='dot')))
    fig.add_trace(go.Scatter(x=["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"], y=[total_monthly_budget]*12, name="Budget", line=dict(color=MOM_COLOR_BUD)))
    fig.add_trace(go.Scatter(x=["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"], y=vals_curr, name=f"{selected_year}", line=dict(color=MOM_COLOR_CURR, width=4)))
    fig.update_layout(title="Evolución Mensual", template="plotly_white", height=500, legend=dict(orientation="h", y=1.02))
    return fig

def plot_comparison_bars(df_curr, df_prev, year_curr, year_prev, budgets_ceco_adj):
    grp_c, grp_p = df_curr.groupby('Desc_Ceco')['Gasto_Real'].sum(), df_prev.groupby('Desc_Ceco')['Gasto_Real'].sum()
    all_c = sorted(list(set(grp_c.index) | set(grp_p.index) | set(budgets_ceco_adj.index)))
    
    vals_c, vals_p, vals_b = [grp_c.get(c,0) for c in all_c], [grp_p.get(c,0) for c in all_c], [budgets_ceco_adj.get(c,0) for c in all_c]
    all_c.append("TOTAL"); vals_c.append(sum(vals_c)); vals_p.append(sum(vals_p)); vals_b.append(sum(vals_b))

    fig = go.Figure()
    fig.add_trace(go.Bar(x=all_c, y=vals_p, name=str(year_prev), marker_color=MOM_COLOR_PREV, text=[f"${v:,.0f}" for v in vals_p], textposition='auto'))
    fig.add_trace(go.Bar(x=all_c, y=vals_c, name=str(year_curr), marker_color=MOM_COLOR_CURR, text=[f"${v:,.0f}" for v in vals_c], textposition='auto'))
    fig.add_trace(go.Scatter(x=all_c, y=vals_b, name="Budget", mode='lines+markers', line=dict(color=MOM_COLOR_BUD, dash='dot')))
    fig.update_layout(title=f"Comparativa {year_prev} vs {year_curr}", barmode='group', template="plotly_white", height=600)
    return fig

# ==============================================================================
# MAIN APP
# ==============================================================================
def main():
    st.title("📉 Dashboard Control SGA")
    
    with st.spinner('Cargando archivos Excel...'):
        df, msg = load_data_from_excel(DATA_FILENAME)
        df_bud = load_budget_excel(BUDGET_FILENAME)
    
    if df is None: st.error(msg); return
    else: st.success(msg)

    st.sidebar.header("Filtros")
    years = sorted(df['Fecha'].dt.year.unique())
    if not years: st.error("Sin datos de fecha."); return
    
    sel_year = st.sidebar.selectbox("Año Fiscal", years, index=len(years)-1)
    df_y = df[df['Fecha'].dt.year == sel_year]
    months = sorted(df_y['Fecha'].dt.month.unique())
    if not months: st.warning("Sin datos este año."); return

    m_names = {1:"Ene", 2:"Feb", 3:"Mar", 4:"Abr", 5:"May", 6:"Jun", 7:"Jul", 8:"Ago", 9:"Sep", 10:"Oct", 11:"Nov", 12:"Dic"}
    sel_month = st.sidebar.selectbox("Mes Cierre", months, format_func=lambda x: f"{x}-{m_names[x]}", index=len(months)-1)
    view = st.sidebar.radio("Vista", ["MTD", "YTD"], horizontal=True)
    
    target = datetime.datetime(sel_year, sel_month, 1)
    if "MTD" in view:
        df_f = df_y[df_y['Fecha'] == target].copy()
        df_fp = df[(df['Fecha'].dt.year == sel_year-1) & (df['Fecha'].dt.month == sel_month)].copy()
        factor = 1.0/12.0
        lbl = f"Mensual ({m_names[sel_month]})"
    else:
        df_f = df_y[df_y['Fecha'] <= target].copy()
        df_fp = df[(df['Fecha'].dt.year == sel_year-1) & (df['Fecha'].dt.month <= sel_month)].copy()
        factor = float(sel_month)/12.0
        lbl = f"YTD (Ene-{m_names[sel_month]})"

    bud_ceco = df_bud.groupby('Desc_Ceco')['Budget_Anual'].sum() * factor
    
    # --- HELPER PARA MOSTRAR KPIS (ACTUALIZADO CON TEXTO DE AHORRO/EXCESO) ---
    def mostrar_kpis(budget, real, prior, prior_label):
        diff_bud = real - budget
        pct_bud = (diff_bud / budget * 100) if budget else 0
        diff_prior = real - prior
        pct_prior = (diff_prior / prior * 100) if prior else 0
        
        # LOGICA DE TEXTO PARA LA BURBUJA
        if diff_bud < 0:
            lbl_bud_txt = "Ahorro"
        else:
            lbl_bud_txt = "Exceso"
        
        # El delta combina el % absoluto + la palabra
        delta_text_bud = f"{pct_bud:.1f}% {lbl_bud_txt}"

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Budget", f"${budget:,.0f}")
        c2.metric("Real", f"${real:,.0f}", f"{diff_bud:+,.0f}", delta_color="inverse")
        
        # AQUI SE APLICA EL CAMBIO SOLICITADO
        c3.metric("Var vs Bud", f"{pct_bud:+.1f}%", delta_text_bud, delta_color="inverse")
        
        c4.metric(f"Vs {prior_label}", f"{pct_prior:+.1f}%", f"{diff_prior:+,.0f}", delta_color="inverse")

    tab1, tab2, tab3 = st.tabs(["Waterfall", "Evolución", "Comparativa"])
    
    with tab1:
        act_ceco = df_f.groupby('Desc_Ceco')['Gasto_Real'].sum()
        all_c = sorted(list(set(act_ceco.index) | set(bud_ceco.index)))
        tot_b, tot_r, tot_p = bud_ceco.sum(), act_ceco.sum(), df_fp['Gasto_Real'].sum()

        lbls, vals, meas, bar_v, bar_t = ["Budget Total"], [tot_b], ["absolute"], [tot_b], [f"${tot_b:,.0f}"]
        
        for c in all_c:
            a, b = act_ceco.get(c,0), bud_ceco.get(c,0)
            if abs(a-b)>1:
                lbls.append(c); vals.append(a-b); meas.append("relative"); bar_v.append(a)
                bar_t.append(f"${a:,.0f}" + (f"<br>({a/b*100:.1f}%)" if b!=0 else ""))
        
        lbls.append("Total Real"); vals.append(tot_r); meas.append("total"); bar_v.append(tot_r); bar_t.append(f"${tot_r:,.0f}")
        
        st.subheader(f"Variación {lbl}")
        
        # 1. MOSTRAR KPIS PRINCIPALES
        mostrar_kpis(tot_b, tot_r, tot_p, str(sel_year-1))

        # GRAFICO PRINCIPAL
        sel = st.plotly_chart(plot_waterfall_generic(lbls, vals, meas, bar_v, f"Waterfall {lbl}", False, False, bar_t, tot_p, f"Real {sel_year-1}"), use_container_width=True, on_select="rerun")
        
        # --- LOGICA DE DRILL DOWN ---
        clk = sel["selection"]["points"][0]["x"] if sel and sel["selection"]["points"] else None
        
        if clk:
            if clk == "Total Real":
                st.markdown(f"--- \n ### 🌎 Zoom Global: Desglose por Concepto")
                
                # En vista global, los totales son los mismos
                mostrar_kpis(tot_b, tot_r, tot_p, str(sel_year-1))

                grp_r = df_f.groupby('Concepto_Norm')['Gasto_Real'].sum()
                grp_b = df_bud.groupby('Concepto_Norm')['Budget_Anual'].sum() * factor
                
                d_lbls, d_vals, d_meas, d_bar = ["Budget Global"], [grp_b.sum()], ["absolute"], [grp_b.sum()]
                
                for concept in sorted(list(set(grp_r.index)|set(grp_b.index))):
                    vr, vb = grp_r.get(concept,0), grp_b.get(concept,0)
                    if abs(vr-vb)>1:
                        d_lbls.append(concept); d_vals.append(vr-vb); d_meas.append("relative"); d_bar.append(vr)
                        
                d_lbls.append("Total Real"); d_vals.append(grp_r.sum()); d_meas.append("total"); d_bar.append(grp_r.sum())
                
                st.plotly_chart(plot_waterfall_generic(d_lbls, d_vals, d_meas, d_bar, f"Variación Global vs Budget ({lbl})", True), use_container_width=True)

            elif clk not in ["Budget Total", f"Real {sel_year-1}"]:
                st.markdown(f"--- \n ### 🔎 Detalle: {clk}")
                df_c_r = df_f[df_f['Desc_Ceco']==clk]
                df_c_b = df_bud[df_bud['Desc_Ceco']==clk]
                df_c_p = df_fp[df_fp['Desc_Ceco']==clk] 
                
                ceco_real = df_c_r['Gasto_Real'].sum()
                ceco_bud = df_c_b['Budget_Anual'].sum() * factor
                ceco_prior = df_c_p['Gasto_Real'].sum()
                
                # 2. MOSTRAR KPIS ESPECIFICOS DEL CECO
                mostrar_kpis(ceco_bud, ceco_real, ceco_prior, str(sel_year-1))
                
                grp_r = df_c_r.groupby('Concepto_Norm')['Gasto_Real'].sum()
                grp_b = df_c_b.groupby('Concepto_Norm')['Budget_Anual'].sum() * factor
                
                d_lbls, d_vals, d_meas, d_bar = ["Budget"], [grp_b.sum()], ["absolute"], [grp_b.sum()]
                for concept in sorted(list(set(grp_r.index)|set(grp_b.index))):
                    vr, vb = grp_r.get(concept,0), grp_b.get(concept,0)
                    if abs(vr-vb)>1:
                        d_lbls.append(concept); d_vals.append(vr-vb); d_meas.append("relative"); d_bar.append(vr)
                d_lbls.append("Real"); d_vals.append(grp_r.sum()); d_meas.append("total"); d_bar.append(grp_r.sum())
                
                st.plotly_chart(plot_waterfall_generic(d_lbls, d_vals, d_meas, d_bar, f"Detalle {clk}", True), use_container_width=True)

    with tab2: st.plotly_chart(plot_mom_evolution(df, sel_year, df_bud['Budget_Anual'].sum()/12), use_container_width=True)
    with tab3: st.plotly_chart(plot_comparison_bars(df_f, df_fp, sel_year, sel_year-1, bud_ceco), use_container_width=True)

if __name__ == "__main__":
    main()

