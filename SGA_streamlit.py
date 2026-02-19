import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import datetime
import numpy as np
import os
import re

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
# 1. FUNCIONES AUXILIARES Y DE NORMALIZACIÓN
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

def normalize_for_match(text):
    """
    Elimina espacios y caracteres especiales para facilitar el match.
    Ej: " Adm. Finanzas. " -> "ADMINANZAS"
    """
    if pd.isna(text): return ""
    # Convertir a string y mayúsculas
    t = str(text).upper()
    # Mantener solo letras y números (elimina espacios, puntos, guiones...)
    t = re.sub(r'[^A-Z0-9]', '', t)
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
        # Aseguramos que Desc_Ceco sea string limpio
        df['Desc_Ceco'] = df['Desc_Ceco'].astype(str).str.upper().str.strip()
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
        # Aseguramos que Desc_Ceco sea string limpio
        df_melt['Desc_Ceco'] = df_melt['Desc_Ceco'].astype(str).str.upper().str.strip()
        df_melt = df_melt[~df_melt['Desc_Ceco'].isin(['NAN', 'NONE', '', 'NAN'])]
        df_melt['Concepto_Norm'] = df_melt['Concepto_Raw'].apply(normalizar_denom3)
        
        return df_melt.groupby(['Desc_Ceco', 'Concepto_Norm'])['Budget_Anual'].sum().reset_index()
    except Exception as e:
        st.error(f"Error leyendo Budget: {e}")
        return pd.DataFrame(columns=['Desc_Ceco', 'Concepto_Norm', 'Budget_Anual'])

@st.cache_data
def create_smart_mapping(filename, target_cecos_list):
    """
    Lee la hoja 'Ceco', normaliza los nombres de ambas fuentes y crea el mapa
    {Desc_Ceco_Original : Responsable_Agrupado}.
    """
    if not os.path.exists(filename): return {}
    try:
        # Leer hoja 'Ceco', columnas B (idx 1) y C (idx 2)
        df_map = pd.read_excel(filename, sheet_name='Ceco', header=0)
        if len(df_map.columns) < 3: return {}
        
        # Extraer columnas relevantes por posición y limpiar NAs
        df_ref = df_map.iloc[:, [1, 2]].dropna()
        col_den_ceco_excel = df_ref.columns[0]
        col_responsable_excel = df_ref.columns[1]

        # 1. Crear clave normalizada en el Excel (la "huella digital")
        df_ref['match_key'] = df_ref[col_den_ceco_excel].apply(normalize_for_match)
        
        # Crear diccionario de búsqueda: {Huella_Digital_Excel : Responsable_Excel}
        # Usamos drop_duplicates para evitar errores si el Excel tiene CeCos repetidos
        df_ref_unique = df_ref.drop_duplicates(subset=['match_key'])
        lookup_dict = dict(zip(df_ref_unique['match_key'], df_ref_unique[col_responsable_excel]))
        
        final_mapping = {}
        # 2. Iterar por los CeCos de nuestros datos (target_cecos_list)
        for ceco_orig in target_cecos_list:
            # Normalizar el CeCo de nuestros datos para buscar su huella
            norm_target = normalize_for_match(ceco_orig)
            
            # Buscar la huella en el diccionario del Excel
            found_resp = lookup_dict.get(norm_target)
            
            if found_resp:
                # Si hay coincidencia, guardamos el mapeo: Nombre Original -> Responsable del Excel
                final_mapping[ceco_orig] = str(found_resp).upper().strip()
            # Si no se encuentra, no se agrega al mapa (luego se llenará con 'SIN ASIGNAR')

        return final_mapping

    except Exception as e:
        st.error(f"Error creando mapeo inteligente: {e}")
        return {}

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
    
    with st.spinner('Cargando datos y mapeos...'):
        # 1. Cargar datos principales
        df, msg = load_data_from_excel(DATA_FILENAME)
        df_bud = load_budget_excel(BUDGET_FILENAME)
        
        if df is None or df_bud.empty:
            st.error("Error cargando datos. Verifique los archivos.")
            return
            
        # 2. Obtener lista única de todos los CeCos en nuestros datos
        all_my_cecos = set(df['Desc_Ceco'].unique()) | set(df_bud['Desc_Ceco'].unique())
        
        # 3. Crear el mapa inteligente usando esa lista
        dict_responsables_smart = create_smart_mapping(BUDGET_FILENAME, all_my_cecos)
        
        # 4. Aplicar el mapa a los dataframes. Los que no hagan match quedan como 'SIN ASIGNAR'
        df['Responsable'] = df['Desc_Ceco'].map(dict_responsables_smart).fillna('SIN ASIGNAR')
        df_bud['Responsable'] = df_bud['Desc_Ceco'].map(dict_responsables_smart).fillna('SIN ASIGNAR')

    st.success(msg)

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

    # Calcular budget total por CeCo (para el primer tab)
    bud_ceco = df_bud.groupby('Desc_Ceco')['Budget_Anual'].sum() * factor
    
    # --- HELPER PARA MOSTRAR KPIS ---
    def mostrar_kpis(budget, real, prior, prior_label):
        diff_bud = real - budget
        pct_bud = (diff_bud / budget * 100) if budget else 0
        diff_prior = real - prior
        pct_prior = (diff_prior / prior * 100) if prior else 0
        
        if diff_bud < 0:
            delta_text_bud = f"-{abs(pct_bud):.1f}% Ahorro"
        elif diff_bud > 0:
            delta_text_bud = f"+{abs(pct_bud):.1f}% Exceso"
        else:
            delta_text_bud = "0.0% Igual"

        if diff_prior < 0: delta_text_prior = f"-{abs(diff_prior):,.0f}"
        else: delta_text_prior = f"+{abs(diff_prior):,.0f}"

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Budget", f"${budget:,.0f}")
        c2.metric("Real", f"${real:,.0f}", f"{diff_bud:+,.0f}", delta_color="inverse")
        c3.metric("Var vs Bud", f"{pct_bud:+.1f}%", delta_text_bud, delta_color="inverse")
        c4.metric(f"Vs {prior_label}", f"{pct_prior:+.1f}%", delta_text_prior, delta_color="inverse")

    # --- TABS ---
    tab_ceco, tab_resp, tab_evo, tab_comp = st.tabs(["Waterfall por CeCo", "Waterfall por Responsable", "Evolución", "Comparativa"])
    
    # ==============================================================================
    # TAB 1: WATERFALL POR CECO (Sin cambios en lógica visual)
    # ==============================================================================
    with tab_ceco:
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
        
        st.subheader(f"Variación por Centro de Costo ({lbl})")
        mostrar_kpis(tot_b, tot_r, tot_p, str(sel_year-1))

        sel = st.plotly_chart(plot_waterfall_generic(lbls, vals, meas, bar_v, f"Waterfall CeCo {lbl}", False, False, bar_t, tot_p, f"Real {sel_year-1}"), use_container_width=True, on_select="rerun", key="wf_ceco_main")
        
        clk = sel["selection"]["points"][0]["x"] if sel and sel["selection"]["points"] else None
        if clk:
            if clk == "Total Real":
                st.markdown(f"--- \n ### 🌎 Zoom Global: Desglose por Concepto")
                mostrar_kpis(tot_b, tot_r, tot_p, str(sel_year-1))
                grp_r = df_f.groupby('Concepto_Norm')['Gasto_Real'].sum()
                grp_b = df_bud.groupby('Concepto_Norm')['Budget_Anual'].sum() * factor
                d_lbls, d_vals, d_meas, d_bar = ["Budget Global"], [grp_b.sum()], ["absolute"], [grp_b.sum()]
                for concept in sorted(list(set(grp_r.index)|set(grp_b.index))):
                    vr, vb = grp_r.get(concept,0), grp_b.get(concept,0)
                    if abs(vr-vb)>1:
                        d_lbls.append(concept); d_vals.append(vr-vb); d_meas.append("relative"); d_bar.append(vr)
                d_lbls.append("Total Real"); d_vals.append(grp_r.sum()); d_meas.append("total"); d_bar.append(grp_r.sum())
                st.plotly_chart(plot_waterfall_generic(d_lbls, d_vals, d_meas, d_bar, f"Variación Global vs Budget ({lbl})", True), use_container_width=True, key="wf_ceco_drill_global")
            elif clk not in ["Budget Total", f"Real {sel_year-1}"]:
                st.markdown(f"--- \n ### 🔎 Detalle CeCo: {clk}")
                df_c_r = df_f[df_f['Desc_Ceco']==clk]
                df_c_b = df_bud[df_bud['Desc_Ceco']==clk]
                df_c_p = df_fp[df_fp['Desc_Ceco']==clk] 
                mostrar_kpis(df_c_b['Budget_Anual'].sum() * factor, df_c_r['Gasto_Real'].sum(), df_c_p['Gasto_Real'].sum(), str(sel_year-1))
                grp_r = df_c_r.groupby('Concepto_Norm')['Gasto_Real'].sum()
                grp_b = df_c_b.groupby('Concepto_Norm')['Budget_Anual'].sum() * factor
                d_lbls, d_vals, d_meas, d_bar = ["Budget"], [grp_b.sum()], ["absolute"], [grp_b.sum()]
                for concept in sorted(list(set(grp_r.index)|set(grp_b.index))):
                    vr, vb = grp_r.get(concept,0), grp_b.get(concept,0)
                    if abs(vr-vb)>1:
                        d_lbls.append(concept); d_vals.append(vr-vb); d_meas.append("relative"); d_bar.append(vr)
                d_lbls.append("Real"); d_vals.append(grp_r.sum()); d_meas.append("total"); d_bar.append(grp_r.sum())
                st.plotly_chart(plot_waterfall_generic(d_lbls, d_vals, d_meas, d_bar, f"Detalle {clk}", True), use_container_width=True, key="wf_ceco_drill_detail")

    # ==============================================================================
    # TAB 2: WATERFALL POR RESPONSABLE (AGRUPADO)
    # ==============================================================================
    with tab_resp:
        # Agrupamos por la nueva columna 'Responsable' que ya tiene el mapeo inteligente
        bud_resp = df_bud.groupby('Responsable')['Budget_Anual'].sum() * factor
        act_resp = df_f.groupby('Responsable')['Gasto_Real'].sum()
        all_r = sorted(list(set(act_resp.index) | set(bud_resp.index)))
        
        # Los totales globales deben coincidir con los del Tab 1
        tot_b, tot_r, tot_p = bud_resp.sum(), act_resp.sum(), df_fp['Gasto_Real'].sum()

        lbls_r, vals_r, meas_r, bar_v_r, bar_t_r = ["Budget Total"], [tot_b], ["absolute"], [tot_b], [f"${tot_b:,.0f}"]
        
        for r in all_r:
            a, b = act_resp.get(r,0), bud_resp.get(r,0)
            # Filtramos variaciones muy pequeñas para limpiar el gráfico
            if abs(a-b)>1:
                lbls_r.append(r); vals_r.append(a-b); meas_r.append("relative"); bar_v_r.append(a)
                bar_t_r.append(f"${a:,.0f}" + (f"<br>({a/b*100:.1f}%)" if b!=0 else ""))
        
        lbls_r.append("Total Real"); vals_r.append(tot_r); meas_r.append("total"); bar_v_r.append(tot_r); bar_t_r.append(f"${tot_r:,.0f}")
        
        st.subheader(f"Variación por Responsable ({lbl})")
        mostrar_kpis(tot_b, tot_r, tot_p, str(sel_year-1))

        sel_resp = st.plotly_chart(plot_waterfall_generic(lbls_r, vals_r, meas_r, bar_v_r, f"Waterfall Responsable {lbl}", False, False, bar_t_r, tot_p, f"Real {sel_year-1}"), use_container_width=True, on_select="rerun", key="wf_resp_main")
        
        clk_resp = sel_resp["selection"]["points"][0]["x"] if sel_resp and sel_resp["selection"]["points"] else None
        if clk_resp:
            if clk_resp == "Total Real":
                st.markdown(f"--- \n ### 🌎 Zoom Global: Desglose por Concepto")
                mostrar_kpis(tot_b, tot_r, tot_p, str(sel_year-1))
                grp_r = df_f.groupby('Concepto_Norm')['Gasto_Real'].sum()
                grp_b = df_bud.groupby('Concepto_Norm')['Budget_Anual'].sum() * factor
                d_lbls_r, d_vals_r, d_meas_r, d_bar_r = ["Budget Global"], [grp_b.sum()], ["absolute"], [grp_b.sum()]
                for concept in sorted(list(set(grp_r.index)|set(grp_b.index))):
                    vr, vb = grp_r.get(concept,0), grp_b.get(concept,0)
                    if abs(vr-vb)>1:
                        d_lbls_r.append(concept); d_vals_r.append(vr-vb); d_meas_r.append("relative"); d_bar_r.append(vr)
                d_lbls_r.append("Total Real"); d_vals_r.append(grp_r.sum()); d_meas_r.append("total"); d_bar_r.append(grp_r.sum())
                st.plotly_chart(plot_waterfall_generic(d_lbls_r, d_vals_r, d_meas_r, d_bar_r, f"Variación Global vs Budget ({lbl})", True), use_container_width=True, key="wf_resp_drill_global")
            elif clk_resp not in ["Budget Total", f"Real {sel_year-1}"]:
                st.markdown(f"--- \n ### 🔎 Detalle Responsable: {clk_resp}")
                # Filtramos por el Responsable seleccionado
                df_resp_r = df_f[df_f['Responsable']==clk_resp]
                df_resp_b = df_bud[df_bud['Responsable']==clk_resp]
                df_resp_p = df_fp[df_fp['Responsable']==clk_resp] 
                mostrar_kpis(df_resp_b['Budget_Anual'].sum() * factor, df_resp_r['Gasto_Real'].sum(), df_resp_p['Gasto_Real'].sum(), str(sel_year-1))
                grp_r_r = df_resp_r.groupby('Concepto_Norm')['Gasto_Real'].sum()
                grp_b_r = df_resp_b.groupby('Concepto_Norm')['Budget_Anual'].sum() * factor
                d_lbls_r, d_vals_r, d_meas_r, d_bar_r = ["Budget"], [grp_b_r.sum()], ["absolute"], [grp_b_r.sum()]
                for concept in sorted(list(set(grp_r_r.index)|set(grp_b_r.index))):
                    vr, vb = grp_r_r.get(concept,0), grp_b_r.get(concept,0)
                    if abs(vr-vb)>1:
                        d_lbls_r.append(concept); d_vals_r.append(vr-vb); d_meas_r.append("relative"); d_bar_r.append(vr)
                d_lbls_r.append("Real"); d_vals_r.append(grp_r_r.sum()); d_meas_r.append("total"); d_bar_r.append(grp_r_r.sum())
                st.plotly_chart(plot_waterfall_generic(d_lbls_r, d_vals_r, d_meas_r, d_bar_r, f"Detalle {clk_resp}", True), use_container_width=True, key="wf_resp_drill_detail")

    # ==============================================================================
    # TAB 3 y 4: EVOLUCIÓN Y COMPARATIVA
    # ==============================================================================
    with tab_evo: st.plotly_chart(plot_mom_evolution(df, sel_year, df_bud['Budget_Anual'].sum()/12), use_container_width=True)
    with tab_comp: st.plotly_chart(plot_comparison_bars(df_f, df_fp, sel_year, sel_year-1, bud_ceco), use_container_width=True)

if __name__ == "__main__":
    main()
