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

@st.cache_data
def load_ceco_mapping(excel_path):
    if not os.path.exists(excel_path):
        return {}
    try:
        df_map = pd.read_excel(excel_path, sheet_name="Ceco")
        col_den = 'Den Ceco'
        col_agrup = 'Agrup. Ceco'
        
        if col_den not in df_map.columns or col_agrup not in df_map.columns:
             st.warning("No se encontraron las columnas 'Den Ceco' o 'Agrup. Ceco' en la pestaña 'Ceco'.")
             return {}

        df_map = df_map.dropna(subset=[col_den, col_agrup])
        df_map[col_den] = df_map[col_den].astype(str).str.upper().str.strip()
        df_map[col_agrup] = df_map[col_agrup].astype(str).str.strip()
        
        mapping_dict = df_map.set_index(col_den)[col_agrup].to_dict()
        
        # --- EXCEPCIONES PARA ABREVIATURAS Y EL CECO VIRTUAL ---
        excepciones = {
            "INT.TRANSP.CST": "Sales & CSR's",
            "CUS.TRANSP.CST": "Sales & CSR's",
            "SELLING - OTHER DIR.": "Sales & CSR's",
            "SELLING - OTHER IND.": "Sales & CSR's",
            "RE-INVOICED (AGRUPADO)": "Sales & CSR's"
        }
        
        for abrev, asignacion in excepciones.items():
            mapping_dict[abrev] = asignacion
            
        return mapping_dict

    except Exception as e:
        st.warning(f"No se pudo cargar la pestaña 'Ceco' para agrupación: {e}")
        return {}

# ==============================================================================
# 3. GRÁFICOS
# ==============================================================================
def plot_waterfall_generic(labels, wf_values, wf_measures, bar_values, title, is_drilldown=False, simple_bar_mode=False, bar_custom_text=None, val_prior_year=None, label_prior_year="Año Ant"):
    fig = go.Figure()

    if val_prior_year is not None:
        labels.insert(0, label_prior_year)
        wf_values.insert(0, val_prior_year)
        wf_measures.insert(0, "absolute")
        bar_values.insert(0, val_prior_year)
        if bar_custom_text:
            bar_custom_text.insert(0, f"${val_prior_year:,.0f}")

    bg_colors = []
    bg_widths = [] 

    for i, measure in enumerate(wf_measures):
        if val_prior_year is not None and i == 0:
             bg_colors.append(MOM_COLOR_PREV)
             bg_widths.append(0.9) 
        elif not simple_bar_mode and i == (1 if val_prior_year is not None else 0):
             bg_colors.append(MOM_COLOR_BUD)
             bg_widths.append(0.9) 
        elif measure == "total" or labels[i] in ["Real Total", "Real Global", "Real Ceco", "Real Grupo", "Total Real"]:
             bg_colors.append(COLOR_TOTALS)
             bg_widths.append(0.9) 
        else:
             bg_colors.append(COLOR_BARS_REAL)
             bg_widths.append(0.9 if simple_bar_mode else 0.7) 

    if bar_custom_text:
        text_list_bar = bar_custom_text
    else:
        text_list_bar = [f"${v:,.0f}" if v != 0 else "" for v in bar_values]

    wf_text_list = []
    for i, measure in enumerate(wf_measures):
        if measure in ["absolute", "total"]:
            wf_text_list.append("")
        else:
            wf_text_list.append(f"${wf_values[i]:,.0f}")

    fig.add_trace(go.Bar(
        name="Gasto Real / Referencia",
        x=labels,
        y=bar_values,
        text=text_list_bar, 
        textposition='outside',
        marker_color=bg_colors,
        width=bg_widths, 
        opacity=1
    ))

    if not simple_bar_mode:
        fig.add_trace(go.Waterfall(
            name="Variación",
            orientation="v",
            measure=wf_measures,
            x=labels,
            y=wf_values,
            text=wf_text_list,
            textposition="outside",
            connector={"line": {"color": COLOR_NEUTRAL, "width": 1}},
            increasing = {"marker": {"color": COLOR_BAD}}, 
            decreasing = {"marker": {"color": COLOR_GOOD}},
            totals     = {"marker": {"color": "rgba(0,0,0,0)"}},
            width=0.9 
        ))

    fig.update_layout(
        title=title,
        yaxis_title="Monto ($)",
        template="plotly_white",
        barmode='overlay', 
        height=600 if is_drilldown else 700,
        showlegend=False,
        waterfallgap=0.1,
        hovermode="x unified",
        margin=dict(t=80)
    )
    return fig

def plot_mom_evolution(df_all, selected_year, total_monthly_budget):
    prior_year = selected_year - 1
    df_curr = df_all[df_all['Fecha'].dt.year == selected_year].copy()
    df_prev = df_all[df_all['Fecha'].dt.year == prior_year].copy()
    
    months_num = list(range(1, 13))
    months_txt = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    
    def get_monthly_vals(dframe):
        if dframe.empty: return [0]*12
        g = dframe.groupby(dframe['Fecha'].dt.month)['Gasto_Real'].sum()
        return [g.get(m, 0.0) for m in months_num]

    vals_curr = get_monthly_vals(df_curr)
    vals_prev = get_monthly_vals(df_prev)
    vals_bud = [total_monthly_budget] * 12 
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=months_txt, y=vals_prev, mode='lines+markers', name=f"Real {prior_year}", line=dict(color=MOM_COLOR_PREV, width=2, dash='dot'), marker=dict(size=6)))
    fig.add_trace(go.Scatter(x=months_txt, y=vals_bud, mode='lines', name="Budget Mensual", line=dict(color=MOM_COLOR_BUD, width=3)))
    fig.add_trace(go.Scatter(x=months_txt, y=vals_curr, mode='lines+markers', name=f"Real {selected_year}", line=dict(color=MOM_COLOR_CURR, width=4), marker=dict(size=8)))
    
    fig.update_layout(title=f"Evolución Mensual (MoM): {prior_year} vs {selected_year} vs Budget", xaxis_title="Mes", yaxis_title="Gasto ($)", template="plotly_white", height=550, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

def plot_comparison_bars(df_curr, df_prev, year_curr, year_prev, budgets_ceco_adj_series):
    grp_curr = df_curr.groupby('Desc_Ceco')['Gasto_Real'].sum()
    grp_prev = df_prev.groupby('Desc_Ceco')['Gasto_Real'].sum()
    budgets_dict = budgets_ceco_adj_series.to_dict()
    all_cecos = sorted(list(set(grp_curr.index) | set(grp_prev.index) | set(budgets_dict.keys())))
    
    vals_curr = []
    vals_prev = []
    vals_bud = []
    
    for c in all_cecos:
        vals_curr.append(grp_curr.get(c, 0.0))
        vals_prev.append(grp_prev.get(c, 0.0))
        vals_bud.append(budgets_dict.get(c, 0.0))
    all_cecos.append("TOTAL")
    vals_curr.append(sum(vals_curr))
    vals_prev.append(sum(vals_prev))
    vals_bud.append(sum(vals_bud))
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=all_cecos, y=vals_prev, name=str(year_prev), marker_color=MOM_COLOR_PREV, text=[f"${v:,.0f}" for v in vals_prev], textposition='auto', opacity=0.8))
    fig.add_trace(go.Bar(x=all_cecos, y=vals_curr, name=str(year_curr), marker_color=MOM_COLOR_CURR, text=[f"${v:,.0f}" for v in vals_curr], textposition='auto', opacity=0.9))
    fig.add_trace(go.Scatter(x=all_cecos, y=vals_bud, name="Budget", mode='lines+markers', line=dict(color=MOM_COLOR_BUD, width=3, dash='dot'), marker=dict(size=10, symbol='diamond', color=MOM_COLOR_BUD), text=[f"${v:,.0f}" for v in vals_bud]))
    
    fig.update_layout(title=f"Comparativa Nivel de Gasto: {year_prev} vs {year_curr}", xaxis_title="Centro de Costo", yaxis_title="Gasto ($)", barmode='group', template="plotly_white", height=650, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

# ==============================================================================
# MAIN APP
# ==============================================================================
def main():
    st.markdown("""
        <style>
            .main .block-container { padding-bottom: 300px !important; min-height: 120vh !important; }
            [data-testid="stSidebar"] > div:first-child { padding-bottom: 300px !important; }
            section[data-testid="stSidebarContent"] { padding-bottom: 300px !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title("📉 Dashboard Control SGA")

    with st.spinner('Procesando datos...'):
        df, msg = load_data_from_excel(DATA_FILENAME)
        df_budgets_db = load_budget_excel(BUDGET_FILENAME)
        ceco_mapping = load_ceco_mapping(BUDGET_FILENAME)
    
    if df is None:
        st.error(msg)
        return
    else:
        # --- CREACIÓN DEL CECO VIRTUAL PARA RE-INVOICED ---
        virtual_ceco_name = "RE-INVOICED (AGRUPADO)"
        df.loc[df['Concepto_Norm'] == 'RE-INVOICED', 'Desc_Ceco'] = virtual_ceco_name
        df_budgets_db.loc[df_budgets_db['Concepto_Norm'] == 'RE-INVOICED', 'Desc_Ceco'] = virtual_ceco_name

        # --- APLICAR MAPEO GENERAL ---
        df['Agrup_Ceco'] = df['Desc_Ceco'].map(ceco_mapping).fillna("SIN AGRUPACION")
        df_budgets_db['Agrup_Ceco'] = df_budgets_db['Desc_Ceco'].map(ceco_mapping).fillna("SIN AGRUPACION")
        st.success(f"✅ Datos listos.")

    st.sidebar.header("🗓️ Filtros")
    years = sorted(df['Fecha'].dt.year.unique())
    selected_year = st.sidebar.selectbox("Año Fiscal", years, index=len(years)-1)
    prior_year = selected_year - 1
    
    df_year = df[df['Fecha'].dt.year == selected_year]
    available_months = sorted(df_year['Fecha'].dt.month.unique())
    
    if not available_months:
        st.warning("Sin datos para el año seleccionado.")
        return
        
    month_names = {1:"Ene", 2:"Feb", 3:"Mar", 4:"Abr", 5:"May", 6:"Jun", 7:"Jul", 8:"Ago", 9:"Sep", 10:"Oct", 11:"Nov", 12:"Dic"}
    current_month_idx = len(available_months) - 1
    selected_month_num = st.sidebar.selectbox("Mes de Cierre", available_months, format_func=lambda x: f"{x} - {month_names[x]}", index=current_month_idx)
    view_mode = st.sidebar.radio("Vista", ["MTD (Mensual)", "YTD (Acumulado)"], horizontal=True)
    
    target_date = datetime.datetime(selected_year, selected_month_num, 1)
    if "MTD" in view_mode:
        df_filtered = df_year[df_year['Fecha'] == target_date].copy()
        df_filtered_prior = df[(df['Fecha'].dt.year == prior_year) & (df['Fecha'].dt.month == selected_month_num)].copy()
        mode_label = f"Mensual ({month_names[selected_month_num]})"
        budget_factor = 1.0 / 12.0 
    else:
        df_filtered = df_year[df_year['Fecha'] <= target_date].copy()
        df_filtered_prior = df[(df['Fecha'].dt.year == prior_year) & (df['Fecha'].dt.month <= selected_month_num)].copy()
        mode_label = f"YTD (Ene-{month_names[selected_month_num]})"
        budget_factor = float(selected_month_num) / 12.0

    budgets_ceco_raw = df_budgets_db.groupby('Desc_Ceco')['Budget_Anual'].sum()
    budgets_ceco_adj = budgets_ceco_raw * budget_factor
    budgets_agrup_raw = df_budgets_db.groupby('Agrup_Ceco')['Budget_Anual'].sum()
    budgets_agrup_adj = budgets_agrup_raw * budget_factor
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Análisis por Agrupación", 
        "📊 Análisis Variación (Ceco)", 
        "📈 Evolución MoM", 
        "📊 Comparativa Anual"
    ])

    # ==========================================================================
    # TAB 1: ANÁLISIS POR AGRUPACIÓN 
    # ==========================================================================
    with tab1:
        st.subheader(f"Análisis por Agrupación: {mode_label}")
        
        actuals_agrup = df_filtered.groupby('Agrup_Ceco')['Gasto_Real'].sum()
        all_agrups = sorted(list(set(actuals_agrup.index) | set(budgets_agrup_adj.index)))
        tot_prior_global_agrup = df_filtered_prior['Gasto_Real'].sum()
        
        wf_a_labels = ["Budget Total"]
        total_bud_agrup = budgets_agrup_adj.sum()
        wf_a_values = [total_bud_agrup]
        wf_a_measures = ["absolute"]
        bar_values_a = [total_bud_agrup]
        bar_text_a = [f"${total_bud_agrup:,.0f}"]
        
        intermediates_agrup = []
        for agrup in all_agrups:
            act = actuals_agrup.get(agrup, 0.0)
            bud = budgets_agrup_adj.get(agrup, 0.0)
            delta = act - bud
            if abs(delta) > 1: 
                if bud != 0:
                    pct_exec = (act / bud) * 100
                    txt = f"${act:,.0f}<br><b>({pct_exec:.1f}%)</b>"
                else:
                    txt = f"${act:,.0f}"
                intermediates_agrup.append({'label': agrup, 'delta': delta, 'act': act, 'txt': txt})
                
        intermediates_agrup.sort(key=lambda x: x['delta'], reverse=True)
        
        for item in intermediates_agrup:
            wf_a_labels.append(item['label'])
            wf_a_values.append(item['delta'])
            wf_a_measures.append("relative")
            bar_values_a.append(item['act'])
            bar_text_a.append(item['txt'])
                
        wf_a_labels.append("Real Total")
        total_real_agrup = actuals_agrup.sum()
        wf_a_values.append(total_real_agrup)
        wf_a_measures.append("total")
        bar_values_a.append(total_real_agrup) 
        
        if total_bud_agrup != 0:
             pct_total_a = (total_real_agrup / total_bud_agrup) * 100
             bar_text_a.append(f"${total_real_agrup:,.0f}<br><b>({pct_total_a:.1f}%)</b>") 
        else:
            bar_text_a.append(f"${total_real_agrup:,.0f}")

        fig_agrup = plot_waterfall_generic(
            wf_a_labels, wf_a_values, wf_a_measures, bar_values_a,
            f"Variación por Agrupación de Ceco ({mode_label})",
            bar_custom_text=bar_text_a,
            val_prior_year=tot_prior_global_agrup,       
            label_prior_year=f"Real {prior_year}"  
        )

        c1a, c2a, c3a, c4a = st.columns(4)
        c1a.metric("Budget Total (Excel)", f"${total_bud_agrup:,.0f}")
        c2a.metric("Gasto Real", f"${total_real_agrup:,.0f}", delta=f"{total_real_agrup - total_bud_agrup:+,.0f}", delta_color="inverse")
        pct_a = ((total_real_agrup - total_bud_agrup) / total_bud_agrup * 100) if total_bud_agrup != 0 else 0
        lbl_a = "Ahorro" if pct_a < 0 else "Exceso"
        c3a.metric("Var vs Budget %", f"{pct_a:+.1f}%", delta=f"{pct_a:+.1f}% {lbl_a}", delta_color="inverse")
        diff_prior_a = total_real_agrup - tot_prior_global_agrup
        pct_prior_a = (diff_prior_a / tot_prior_global_agrup * 100) if tot_prior_global_agrup != 0 else 0
        delta_prior_str_a = f"-${abs(diff_prior_a):,.0f}" if diff_prior_a < 0 else f"+${abs(diff_prior_a):,.0f}"
        c4a.metric(f"Var vs Año Ant. ({prior_year})", f"{pct_prior_a:+.1f}%", delta=delta_prior_str_a, delta_color="inverse")

        selection_agrup = st.plotly_chart(fig_agrup, use_container_width=True, on_select="rerun")

        clicked_agrup = None
        if selection_agrup and "selection" in selection_agrup and selection_agrup["selection"]["points"]:
            point = selection_agrup["selection"]["points"][0]
            clicked_agrup = point["x"]
        
        if clicked_agrup and clicked_agrup not in ["Budget Total", "Real Total", f"Real {prior_year}"]:
             st.markdown("---")
             st.markdown(f"### 🔎 Desglose por Ceco: {clicked_agrup}")
             
             df_filtered_agrup = df_filtered[df_filtered['Agrup_Ceco'] == clicked_agrup]
             df_budgets_agrup = df_budgets_db[df_budgets_db['Agrup_Ceco'] == clicked_agrup]
             df_prior_agrup = df_filtered_prior[df_filtered_prior['Agrup_Ceco'] == clicked_agrup]

             actuals_comp = df_filtered_agrup.groupby('Desc_Ceco')['Gasto_Real'].sum()
             budgets_comp_raw = df_budgets_agrup.groupby('Desc_Ceco')['Budget_Anual'].sum()
             budgets_comp_adj = budgets_comp_raw * budget_factor
             all_components = sorted(list(set(actuals_comp.index) | set(budgets_comp_adj.index)))
             
             tot_prior_comp = df_prior_agrup['Gasto_Real'].sum()
             total_real_comp = actuals_comp.sum()
             total_bud_comp = budgets_comp_adj.sum()

             diff_prior_comp = total_real_comp - tot_prior_comp
             pct_prior_comp = (diff_prior_comp / tot_prior_comp * 100) if tot_prior_comp != 0 else 0
             delta_prior_comp_str = f"-${abs(diff_prior_comp):,.0f}" if diff_prior_comp < 0 else f"+${abs(diff_prior_comp):,.0f}"

             wf_c_labels = []
             wf_c_values = []
             wf_c_measures = []
             bar_values_c = []
             bar_text_c = []
             intermediates_comp = []
             
             if total_bud_comp == 0:
                 st.info(f"💡 El grupo '{clicked_agrup}' no tiene presupuesto. Mostrando composición.")
                 title_drill = f"Desglose Gasto Real - {clicked_agrup}"
                 is_simple_mode = True
                 
                 z1, z2, z3 = st.columns(3)
                 z1.metric("Gasto Real", f"${total_real_comp:,.0f}")
                 z2.metric(f"Año Ant ({prior_year})", f"${tot_prior_comp:,.0f}")
                 z3.metric("Var vs Año Ant", f"{pct_prior_comp:+.1f}%", delta=delta_prior_comp_str, delta_color="inverse")

                 for comp in all_components:
                     act = actuals_comp.get(comp, 0.0)
                     if abs(act) > 1:
                         intermediates_comp.append({'label': comp, 'delta': act, 'act': act, 'txt': f"${act:,.0f}"})
                         
                 intermediates_comp.sort(key=lambda x: x['delta'], reverse=True)
                 
                 for item in intermediates_comp:
                     wf_c_labels.append(item['label'])
                     wf_c_values.append(item['delta'])     
                     wf_c_measures.append("relative")      
                     bar_values_c.append(item['act'])
                     bar_text_c.append(item['txt'])
                 
                 wf_c_labels.append("Total Real")
                 wf_c_values.append(total_real_comp)
                 wf_c_measures.append("total")
                 bar_values_c.append(total_real_comp)
                 bar_text_c.append(f"${total_real_comp:,.0f}")

             else:
                 title_drill = f"Desglose de {clicked_agrup} por Ceco"
                 is_simple_mode = False

                 diff_comp = total_real_comp - total_bud_comp
                 pct_comp = (diff_comp / total_bud_comp * 100) if total_bud_comp != 0 else 0
                 delta_comp_bud_str = f"-${abs(diff_comp):,.0f}" if diff_comp < 0 else f"+${abs(diff_comp):,.0f}"

                 c_d1, c_d2, c_d3, c_d4 = st.columns(4)
                 c_d1.metric(f"Budget {clicked_agrup}", f"${total_bud_comp:,.0f}")
                 c_d2.metric(f"Gasto Real", f"${total_real_comp:,.0f}", delta=delta_comp_bud_str, delta_color="inverse")
                 lbl_comp = "Ahorro" if pct_comp < 0 else "Exceso"
                 c_d3.metric("Var vs Budget", f"{pct_comp:+.1f}%", delta=f"{pct_comp:+.1f}% {lbl_comp}", delta_color="inverse")
                 c_d4.metric(f"Var vs {prior_year}", f"{pct_prior_comp:+.1f}%", delta=delta_prior_comp_str, delta_color="inverse")

                 wf_c_labels.append("Budget Grupo")
                 wf_c_values.append(total_bud_comp)
                 wf_c_measures.append("absolute")
                 bar_values_c.append(total_bud_comp)
                 bar_text_c.append(f"${total_bud_comp:,.0f}")
                 
                 for comp in all_components:
                     act = actuals_comp.get(comp, 0.0)
                     bud = budgets_comp_adj.get(comp, 0.0)
                     delta = act - bud
                     if abs(delta) > 1:
                         if bud != 0:
                             pct_exec = (act / bud) * 100
                             txt = f"${act:,.0f}<br><b>({pct_exec:.1f}%)</b>"
                         else:
                             txt = f"${act:,.0f}"
                         intermediates_comp.append({'label': comp, 'delta': delta, 'act': act, 'txt': txt})

                 intermediates_comp.sort(key=lambda x: x['delta'], reverse=True)
                 
                 for item in intermediates_comp:
                     wf_c_labels.append(item['label'])
                     wf_c_values.append(item['delta'])
                     wf_c_measures.append("relative")
                     bar_values_c.append(item['act'])
                     bar_text_c.append(item['txt'])

                 wf_c_labels.append("Real Grupo")
                 wf_c_values.append(total_real_comp)
                 wf_c_measures.append("total")
                 bar_values_c.append(total_real_comp)
                 bar_text_c.append(f"${total_real_comp:,.0f}")

             fig_comp = plot_waterfall_generic(
                 wf_c_labels, wf_c_values, wf_c_measures, bar_values_c,
                 title_drill, is_drilldown=True, simple_bar_mode=is_simple_mode,
                 bar_custom_text=bar_text_c,
                 val_prior_year=tot_prior_comp,
                 label_prior_year=f"Real {prior_year} (Grupo)"
             )
             st.plotly_chart(fig_comp, use_container_width=True)

    # ==========================================================================
    # TAB 2: WATERFALL & DRILL-DOWN (ORIGINAL POR CECO)
    # ==========================================================================
    with tab2:
        actuals_ceco = df_filtered.groupby('Desc_Ceco')['Gasto_Real'].sum()
        all_cecos = sorted(list(set(actuals_ceco.index) | set(budgets_ceco_adj.index)))
        tot_prior_global = df_filtered_prior['Gasto_Real'].sum()
        
        wf1_labels = ["Budget Total"]
        wf1_values = [budgets_ceco_adj.sum()]
        wf1_measures = ["absolute"]
        bar_values1 = [budgets_ceco_adj.sum()]
        bar_text1 = [f"${budgets_ceco_adj.sum():,.0f}"]
        
        intermediates = []
        for ceco in all_cecos:
            act = actuals_ceco.get(ceco, 0.0)
            bud = budgets_ceco_adj.get(ceco, 0.0)
            delta = act - bud
            if abs(delta) > 1: 
                if bud != 0:
                    pct_exec = (act / bud) * 100
                    txt = f"${act:,.0f}<br><b>({pct_exec:.1f}%)</b>"
                else:
                    txt = f"${act:,.0f}"
                intermediates.append({'label': ceco, 'delta': delta, 'act': act, 'txt': txt})
                
        intermediates.sort(key=lambda x: x['delta'], reverse=True)
        
        for item in intermediates:
            wf1_labels.append(item['label'])
            wf1_values.append(item['delta'])
            wf1_measures.append("relative")
            bar_values1.append(item['act'])
            bar_text1.append(item['txt'])
                
        wf1_labels.append("Real Total")
        total_real = actuals_ceco.sum()
        total_bud = budgets_ceco_adj.sum()
        wf1_values.append(total_real)
        wf1_measures.append("total")
        bar_values1.append(total_real) 
        
        if total_bud != 0:
             pct_total = (total_real / total_bud) * 100
             bar_text1.append(f"${total_real:,.0f}<br><b>({pct_total:.1f}%)</b>") 
        else:
            bar_text1.append(f"${total_real:,.0f}")

        fig_main = plot_waterfall_generic(
            wf1_labels, wf1_values, wf1_measures, bar_values1,
            f"Variación por Centro de Costo ({mode_label})",
            bar_custom_text=bar_text1,
            val_prior_year=tot_prior_global,       
            label_prior_year=f"Real {prior_year}"  
        )

        st.subheader(f"Análisis Principal: {mode_label}")
        
        tot_act = actuals_ceco.sum()
        diff = tot_act - total_bud
        pct = (diff / total_bud * 100) if total_bud != 0 else 0
        diff_prior = tot_act - tot_prior_global
        pct_prior = (diff_prior / tot_prior_global * 100) if tot_prior_global != 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Budget Total (Excel)", f"${total_bud:,.0f}")
        c2.metric("Gasto Real", f"${tot_act:,.0f}", delta=f"{diff:+,.0f}", delta_color="inverse")
        lbl = "Ahorro" if pct < 0 else "Exceso"
        c3.metric("Var vs Budget %", f"{pct:+.1f}%", delta=f"{pct:+.1f}% {lbl}", delta_color="inverse")
        lbl_prior = "Mejor" if diff_prior < 0 else "Peor"
        delta_prior_str = f"-${abs(diff_prior):,.0f}" if diff_prior < 0 else f"+${abs(diff_prior):,.0f}"
        c4.metric(f"Var vs Año Ant. ({prior_year})", f"{pct_prior:+.1f}%", delta=delta_prior_str, delta_color="inverse")

        selection = st.plotly_chart(fig_main, use_container_width=True, on_select="rerun")

        clicked_label = None
        if selection and "selection" in selection and selection["selection"]["points"]:
            point = selection["selection"]["points"][0]
            clicked_label = point["x"]

        if clicked_label:
            if clicked_label in ["Budget Total", "Real Total", f"Real {prior_year}", "Total Real"]:
                pass 
            elif clicked_label == "Real Total" or (clicked_label is None): 
                 pass 
            
            # --- ZOOM GLOBAL ---
            if clicked_label == "Real Total":
                st.markdown("---")
                st.markdown("### 🌎 Zoom Global: Variación por Concepto (Todos los CeCos)")
                
                grp_bud_global_raw = df_budgets_db.groupby('Concepto_Norm')['Budget_Anual'].sum()
                grp_bud_global_adj = grp_bud_global_raw * budget_factor
                grp_real_global = df_filtered.groupby('Concepto_Norm')['Gasto_Real'].sum()
                all_global_concepts = sorted(list(set(grp_real_global.index) | set(grp_bud_global_adj.index)))
                
                z1, z2, z3, z4 = st.columns(4)
                z1.metric("Budget Global", f"${total_bud:,.0f}")
                z2.metric("Real Global", f"${tot_act:,.0f}")
                delta_bud_str = f"-${abs(diff):,.0f}" if diff < 0 else f"+${abs(diff):,.0f}"
                z3.metric("Var vs Budget", f"{pct:+.1f}%", delta=delta_bud_str, delta_color="inverse")
                z4.metric(f"Var vs {prior_year}", f"{pct_prior:+.1f}%", delta=delta_prior_str, delta_color="inverse")
                
                wf2_labels = ["Budget Global"]
                wf2_values = [total_bud]
                wf2_measures = ["absolute"]
                bar_values2 = [total_bud]
                bar_text2 = [f"${total_bud:,.0f}"]
                
                intermediates_global = []
                for concept in all_global_concepts:
                    val_real = grp_real_global.get(concept, 0.0)
                    val_bud = grp_bud_global_adj.get(concept, 0.0)
                    delta = val_real - val_bud
                    if abs(delta) > 1:
                        if val_bud != 0:
                            p = (val_real / val_bud) * 100
                            txt = f"${val_real:,.0f}<br><b>({p:.1f}%)</b>"
                        else:
                            txt = f"${val_real:,.0f}"
                        intermediates_global.append({'label': concept, 'delta': delta, 'act': val_real, 'txt': txt})
                
                intermediates_global.sort(key=lambda x: x['delta'], reverse=True)
                
                for item in intermediates_global:
                    wf2_labels.append(item['label'])
                    wf2_values.append(item['delta'])
                    wf2_measures.append("relative")
                    bar_values2.append(item['act'])
                    bar_text2.append(item['txt'])
                
                wf2_labels.append("Real Global")
                wf2_values.append(tot_act)
                wf2_measures.append("total")
                bar_values2.append(tot_act)
                bar_text2.append(f"${tot_act:,.0f}")
                
                fig_global = plot_waterfall_generic(
                    wf2_labels, wf2_values, wf2_measures, bar_values2,
                    f"Variación Global por Concepto - {mode_label}", is_drilldown=True,
                    bar_custom_text=bar_text2,
                    val_prior_year=tot_prior_global,      
                    label_prior_year=f"Real {prior_year}" 
                )
                st.plotly_chart(fig_global, use_container_width=True)

            # --- ZOOM CECO ---
            elif clicked_label != "Budget Total" and clicked_label != f"Real {prior_year}":
                selected_ceco = clicked_label
                st.markdown("---")
                st.markdown(f"### 🔎 Detalle: {selected_ceco}")
                
                df_ceco_real = df_filtered[df_filtered['Desc_Ceco'] == selected_ceco]
                grp_real = df_ceco_real.groupby('Concepto_Norm')['Gasto_Real'].sum()
                df_ceco_bud = df_budgets_db[df_budgets_db['Desc_Ceco'] == selected_ceco]
                grp_bud_raw = df_ceco_bud.groupby('Concepto_Norm')['Budget_Anual'].sum()
                grp_bud_adj = grp_bud_raw * budget_factor
                all_concepts = sorted(list(set(grp_real.index) | set(grp_bud_adj.index)))
                budget_ceco_total = grp_bud_adj.sum()
                
                df_ceco_prior = df_filtered_prior[df_filtered_prior['Desc_Ceco'] == selected_ceco]
                prior_ceco_total = df_ceco_prior['Gasto_Real'].sum() 
                
                real_ceco_total = grp_real.sum()
                diff_prior_ceco = real_ceco_total - prior_ceco_total
                pct_prior_ceco = (diff_prior_ceco / prior_ceco_total * 100) if prior_ceco_total != 0 else 0
                delta_prior_ceco_str = f"-${abs(diff_prior_ceco):,.0f}" if diff_prior_ceco < 0 else f"+${abs(diff_prior_ceco):,.0f}"
                
                wf2_labels = []
                wf2_values = []     
                wf2_measures = []
                bar_values2 = []
                bar_text2 = []
                is_simple_mode = False 
                
                intermediates_ceco = []

                if budget_ceco_total == 0:
                    st.info("💡 Sin presupuesto. Mostrando composición del gasto.")
                    title_drill = f"Desglose Gasto Real - {selected_ceco}"
                    is_simple_mode = True
                    
                    z1, z2, z3 = st.columns(3)
                    z1.metric("Gasto Real", f"${real_ceco_total:,.0f}")
                    z2.metric(f"Año Ant ({prior_year})", f"${prior_ceco_total:,.0f}")
                    z3.metric("Var vs Año Ant", f"{pct_prior_ceco:+.1f}%", delta=delta_prior_ceco_str, delta_color="inverse")

                    for concept in all_concepts:
                        val_real = grp_real.get(concept, 0.0)
                        if abs(val_real) > 1:
                            intermediates_ceco.append({'label': concept, 'delta': val_real, 'act': val_real, 'txt': f"${val_real:,.0f}"})
                            
                    intermediates_ceco.sort(key=lambda x: x['delta'], reverse=True)
                    
                    for item in intermediates_ceco:
                        wf2_labels.append(item['label'])
                        wf2_values.append(item['delta'])     
                        wf2_measures.append("relative")      
                        bar_values2.append(item['act'])
                        bar_text2.append(item['txt'])
                    
                    wf2_labels.append("Total Real")
                    wf2_values.append(grp_real.sum())
                    wf2_measures.append("total")
                    bar_values2.append(grp_real.sum())
                    bar_text2.append(f"${grp_real.sum():,.0f}")

                else:
                    title_drill = f"Variación vs Budget - {selected_ceco}"
                    is_simple_mode = False
                    
                    diff_ceco = real_ceco_total - budget_ceco_total
                    pct_ceco = (diff_ceco / budget_ceco_total * 100) if budget_ceco_total != 0 else 0
                    delta_ceco_bud_str = f"-${abs(diff_ceco):,.0f}" if diff_ceco < 0 else f"+${abs(diff_ceco):,.0f}"
                    
                    c_d1, c_d2, c_d3, c_d4 = st.columns(4)
                    c_d1.metric(f"Budget {selected_ceco}", f"${budget_ceco_total:,.0f}")
                    c_d2.metric(f"Gasto Real", f"${real_ceco_total:,.0f}", delta=delta_ceco_bud_str, delta_color="inverse")
                    lbl_ceco = "Ahorro" if pct_ceco < 0 else "Exceso"
                    c_d3.metric("Var vs Budget", f"{pct_ceco:+.1f}%", delta=f"{pct_ceco:+.1f}% {lbl_ceco}", delta_color="inverse")
                    c_d4.metric(f"Var vs {prior_year}", f"{pct_prior_ceco:+.1f}%", delta=delta_prior_ceco_str, delta_color="inverse")
                    
                    wf2_labels.append("Budget Ceco")
                    wf2_values.append(budget_ceco_total)
                    wf2_measures.append("absolute")
                    bar_values2.append(budget_ceco_total) 
                    bar_text2.append(f"${budget_ceco_total:,.0f}")
                    
                    for concept in all_concepts:
                        val_real = grp_real.get(concept, 0.0)
                        val_bud = grp_bud_adj.get(concept, 0.0)
                        delta = val_real - val_bud
                        if abs(delta) > 1:
                            if val_bud != 0:
                                p = (val_real / val_bud) * 100
                                txt = f"${val_real:,.0f}<br><b>({p:.1f}%)</b>"
                            else:
                                txt = f"${val_real:,.0f}"
                            intermediates_ceco.append({'label': concept, 'delta': delta, 'act': val_real, 'txt': txt})
                            
                    intermediates_ceco.sort(key=lambda x: x['delta'], reverse=True)
                    
                    for item in intermediates_ceco:
                        wf2_labels.append(item['label'])
                        wf2_values.append(item['delta'])     
                        wf2_measures.append("relative")
                        bar_values2.append(item['act'])
                        bar_text2.append(item['txt'])
                    
                    wf2_labels.append("Real Ceco")
                    wf2_values.append(grp_real.sum())
                    wf2_measures.append("total")
                    bar_values2.append(grp_real.sum())
                    bar_text2.append(f"${grp_real.sum():,.0f}")
                
                fig_drill = plot_waterfall_generic(
                    wf2_labels, wf2_values, wf2_measures, bar_values2,
                    title_drill, is_drilldown=True, simple_bar_mode=is_simple_mode,
                    bar_custom_text=bar_text2,
                    val_prior_year=prior_ceco_total,       
                    label_prior_year=f"Real {prior_year}"  
                )
                st.plotly_chart(fig_drill, use_container_width=True)

    # ==========================================================================
    # TAB 3: EVOLUCIÓN MOM
    # ==========================================================================
    with tab3:
        st.subheader("Evolución Mensual Comparativa")
        budget_mensual_promedio = budgets_ceco_raw.sum() / 12.0
        fig_mom = plot_mom_evolution(df, selected_year, budget_mensual_promedio)
        st.plotly_chart(fig_mom, use_container_width=True)

    # ==========================================================================
    # TAB 4: COMPARATIVA ANUAL 
    # ==========================================================================
    with tab4:
        st.subheader(f"Nivel de Gasto: {prior_year} vs {selected_year}")
        if df_filtered.empty and df_filtered_prior.empty:
            st.warning("No hay datos disponibles para comparar.")
        else:
            fig_comp = plot_comparison_bars(df_filtered, df_filtered_prior, selected_year, prior_year, budgets_ceco_adj)
            st.plotly_chart(fig_comp, use_container_width=True)

    st.sidebar.markdown("<br><br><br>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
