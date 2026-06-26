import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import os
import re
import requests
import json


URL_API_SHEET = st.secrets["URL_API_SHEET"]

def obtener_datos_gsheet():
    try:
        response = requests.get(URL_API_SHEET)
        data = response.json()
        # La primera fila son los encabezados (data[0]), el resto son los datos
        df = pd.DataFrame(data[1:], columns=data[0])

        if 'Fecha_Pago' in df.columns:
            # Convertimos a formato fecha, el 'coerce' maneja los errores
            df['Fecha_Pago'] = pd.to_datetime(df['Fecha_Pago'], errors='coerce')
            # Le damos tu formato: DD/MM/AAAA HH:MM:SS
            df['Fecha_Pago'] = df['Fecha_Pago'].dt.strftime('%d/%m/%Y %H:%M:%S')
            # Si queda vacío (NaN), rellenamos con un guion
            df['Fecha_Pago'] = df['Fecha_Pago'].fillna('-')

        # Limpieza para asegurar que Precio sea número
        df['Precio'] = pd.to_numeric(df['Precio'], errors='coerce').fillna(0)

        return df
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        return pd.DataFrame() # Retorna tabla vacía si falla

def actualizar_datos_gsheet(df):
    try:
        # Convertimos el DataFrame a una lista de listas (incluyendo los encabezados)
        datos_a_enviar = [df.columns.values.tolist()] + df.values.tolist()
        # Hacemos una petición POST a la misma URL para escribir los datos
        response = requests.post(URL_API_SHEET, json=datos_a_enviar)
        if response.status_code != 200:
            st.error("⚠️ Hubo un problema al guardar en la nube.")
    except Exception as e:
        st.error(f"Error al enviar datos a Google Sheets: {e}")

# =========================================================================
# ⚙️ CONFIGURACIÓN DE DISEÑO Y VARIABLES GLOBALES (MODIFICA AQUÍ)
# =========================================================================
LISTA_DESTAJISTAS = [
    "Pablo Barragán (Albañilería)",
    "Andrés (Albañileriá)",
    "Miguel Leyva (Instalaciones)",
    "José López (Pisos)",
    "Guillermo (Pintura)",
    "Gerardo Zamora (yaso y pintura)"
]

# 1. ANCHO DE LA BARRA DE USUARIO Y CONTRASEÑA
ANCHO_LOGIN_ENTRADAS = "200px"    

# 2. ESPACIO ENTRE LOS RENGLONES DE LA TABLA (Usa números negativos para juntarlos más)
ESPACIO_ENTRE_RENGLONES = "8px"

# 4. DISEÑO DE LA ETIQUETA "PAGADO"
TAMANO_LETRA_PAGADO = "14px"
GROSOR_ETIQUETA_PAGADO = "2px -25px" # El 2px es lo grueso (arriba/abajo), el 5px es lo ancho (lados)

TAMANO_LETRA_TABLA = "14px"
TAMANO_LETRA_BOTONES = "12px"
COLOR_FONDO_PROTOTIPO = "#1E3A8A"
COLOR_TEXTO_PROTOTIPO = "#FFFFFF"
# =========================================================================

st.set_page_config(page_title="ERP Destajos EGC", layout="wide")

# CSS Ajustado para forzar el tamaño del login
st.markdown(f"""
<style>
    div[data-testid="stTextInput"] {{
        max-width: {ANCHO_LOGIN_ENTRADAS} !important;
    }}
    .stSelectbox label, .stTextInput label {{
        font-size: {TAMANO_LETRA_TABLA} !important;
    }}
    .stButton > button {{
        font-size: {TAMANO_LETRA_BOTONES} !important;
        width: 100%;
    }}
    div[data-testid="stButton"] button {{
        padding: 1px 5px !important; /* Ajusta el relleno interno (arriba/abajo, lados) */
        font-size: 5px !important;  /* Tamaño de letra específico */
        height: auto !important;     /* Altura automática */
    }}
</style>
""", unsafe_allow_html=True)

if 'usuario' not in st.session_state:
    st.session_state.usuario = None

# --- 1. FORMULARIO DE ACCESO ---
def login():
    st.title("🔐 Control de estimaciones Construcasas")
    st.write("Por favor, introduce tus credenciales para ingresar.")
    
    with st.container():
        usuario = st.text_input("Usuario", key="input_user")
        contrasena = st.text_input("Contraseña", type="password", key="input_pass")
        
        if st.button("Ingresar", use_container_width=False):
            usuarios_validos = {"admin": "1234", "saul": "1234", "auditor": "1234"}
            if usuario in usuarios_validos and usuarios_validos[usuario] == contrasena:
                st.session_state.usuario = usuario
                st.rerun()
            else:
                st.error("❌ Usuario o contraseña incorrectos")

if st.session_state.usuario is None:
    login()
    st.stop()

# --- 2. LECTURA DE GOOGLE SHEETS ---
if 'df' not in st.session_state:
    st.session_state.df = obtener_datos_gsheet()
    # Creamos la copia original al iniciar
    st.session_state.df_original = st.session_state.df.copy()

df = st.session_state.df

@st.dialog("⚠️ CONFIRMACIÓN DE PAGO")
def dialogo_confirmacion(indice, lote, partida, destajista, precio):
    st.warning(f"¿Confirmas el pago de la partida **{partida}** para el **{lote}**?")
    st.markdown(f"**Destajista asignado:** {destajista}")
    st.markdown(f"**Monto a liberar:** `${precio:,.2f}`")
    
    col1, col2 = st.columns(2)
    if col1.button("✅ ACEPTAR"):
        # Guardamos la fecha y hora completa
        ahora = datetime.now()

        # Formato: 26/06/2026 14:30
        fecha_hora_str = ahora.strftime("%d/%m/%Y %H:%M:%S")

        usuario_actual = st.session_state.usuario

        # 1. Actualizamos solo en memoria (sin esperar a internet)
        st.session_state.df.at[indice, 'Estado'] = 'Pagado'
        st.session_state.df.at[indice, 'Destajista'] = destajista
        st.session_state.df.at[indice, 'Fecha_Pago'] = fecha_hora_str
        st.session_state.df.at[indice, 'Usuario'] = usuario_actual
        
        # Recargamos al instante
        st.rerun()

    if col2.button("❌ CANCELAR"):
        st.rerun()

# --- 3. MENÚ DE NAVEGACIÓN ---
st.sidebar.title(f"👷 {st.session_state.usuario}")
menu = st.sidebar.radio("Menú Principal:", ["Registro de Destajos", "Dashboard (Gráficos y Visor)", "Mapa Interactivo"])

# Botón de Guardado Manual
if st.sidebar.button("💾 GUARDAR CAMBIOS"):
    with st.spinner("Sincronizando con Google..."):
        actualizar_datos_gsheet(st.session_state.df)
        # Guardamos una copia "limpia" para comparar después
        st.session_state.df_original = st.session_state.df.copy()
        st.success("¡Datos guardados!")
        st.rerun()

# Aviso de seguridad si hay cambios sin guardar
if 'df_original' in st.session_state:
    if not st.session_state.df.equals(st.session_state.df_original):
        st.sidebar.warning("⚠️ Tienes cambios pendientes. ¡Presiona el botón Guardar!")

if st.sidebar.button("🔒 Cerrar Sesión"):
    st.session_state.usuario = None
    st.rerun()



#conteo de prototipos

def clave_ordenamiento(val):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(val))]
st.sidebar.markdown("---")
st.sidebar.markdown("### 🏗️ Resumen Total")

# Lógica para la tabla de resumen (Independiente del Lote seleccionado)
# Usamos el dataframe completo st.session_state.df
df_unicos = st.session_state.df[['Lote', 'Prototipo']].drop_duplicates()
resumen_df = df_unicos.groupby('Prototipo').size().reset_index(name='Cantidad')
resumen_df = resumen_df.sort_values(by='Prototipo', key=lambda x: x.map(clave_ordenamiento))




# Centrar valores y mostrar solo 2 columnas
resumen_df_final = resumen_df.rename(columns={'Prototipo': 'Proto', 'Cantidad': 'Total'}).set_index('Proto')
st.sidebar.table(resumen_df_final)

# 2. Inyectamos CSS para centrar específicamente los valores de esa tabla
st.sidebar.markdown("""
<style>
    /* Centra los encabezados y las celdas de las tablas en el sidebar */
    [data-testid="stSidebar"] table {
        margin-left: auto;
        margin-right: auto;
    }
    [data-testid="stSidebar"] table th {
        text-align: center !important;
    }
    [data-testid="stSidebar"] table td {
        text-align: center !important;
    }
</style>
""", unsafe_allow_html=True)




# Sumatoria total debajo de la columna Total
total_general = resumen_df['Cantidad'].sum()
st.sidebar.markdown(f"**Total Prototipos: {total_general}**")    




# =========================================================================
# PESTAÑA 1: REGISTRO DE DESTAJOS
# =========================================================================
if menu == "Registro de Destajos":
    st.title("📝 Control de Pagos Destajos/Subcontratos")      
       

    # 1. Ajuste de ancho de selectores (Lote y Fecha son más pequeños por usar proporciones 2, 2, 4)
    col_lote, col_fecha, col_vacio = st.columns([2 ,2 ,4])
    lotes_unicos = df['Lote'].unique()
    
    if "lote_seleccionado" not in st.session_state or st.session_state.lote_seleccionado not in lotes_unicos:
        st.session_state.lote_seleccionado = lotes_unicos[0] if len(lotes_unicos) > 0 else ""
        
    col_lote.selectbox("🔍 Selecciona el Lote:", lotes_unicos, key="lote_seleccionado")
    lote_activo = st.session_state.lote_seleccionado 
    
    fecha_filtro = col_fecha.date_input("📅 Filtrar por Fecha de Pago (Opcional):", value=None,format="DD/MM/YYYY")

    df_lote = df[df['Lote'] == lote_activo]
    prototipo = df_lote['Prototipo'].iloc[0] if not df_lote.empty else "N/A"
    terreno = df_lote['Terreno_m2'].iloc[0] if not df_lote.empty else 0
    construccion = df_lote['Construccion_m2'].iloc[0] if not df_lote.empty else 0

    costo_total_filtrado = df_lote['Precio'].sum()
    pagado_filtrado = df_lote[df_lote['Estado'] == 'Pagado']['Precio'].sum()
    pendiente_filtrado = df_lote[df_lote['Estado'] != 'Pagado']['Precio'].sum()

    st.markdown(f"""
    <div style="background-color:{COLOR_FONDO_PROTOTIPO}; padding:20px; border-radius:10px; margin-bottom:20px; color:{COLOR_TEXTO_PROTOTIPO};">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; margin-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.3); padding-bottom: 10px;">
            <div style="font-size:24px; font-weight:bold;">🏠 Lote {lote_activo} - Prototipo {prototipo}</div>
            <div style="font-size:16px;">📐 Terreno: {terreno} m² | Construcción: {construccion} m²</div>
        </div>
        <div style="display: flex; justify-content: space-between; gap: 15px; flex-wrap: wrap;">
            <div style="flex: 1; text-align: center; background-color:rgba(255,255,255,0.1); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Costo Total Prototipo en este Lote</div>
                <div style="font-size:24px; font-weight:bold;">${costo_total_filtrado:,.2f}</div>
            </div>
            <div style="flex: 1; text-align: center; background-color:rgba(16, 185, 129, 0.4); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Total Pagado</div>
                <div style="font-size:24px; font-weight:bold;">${pagado_filtrado:,.2f}</div>
            </div>
            <div style="flex: 1; text-align: center; background-color:rgba(239, 68, 68, 0.5); padding: 15px; border-radius:8px;">
                <div style="font-size:14px; opacity: 0.9;">Total por Pagar</div>
                <div style="font-size:24px; font-weight:bold;">${pendiente_filtrado:,.2f}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
      
    st.markdown("##### ⏳ Filtros de Tabla")
    f_col1, f_col2, f_col3 = st.columns([2, 2, 2])
    filtro_concepto = f_col1.text_input("Buscar Concepto:", "", placeholder="Ej. Muros")
    filtro_destajista = f_col2.selectbox("Filtrar por Destajista:", ["Todos"] + LISTA_DESTAJISTAS)
    filtro_estado = f_col3.selectbox("Filtrar por Estado de Pago:", ["Todos", "Pendiente", "Pagado"])
    
    df_filtrado = df_lote.copy()
    if filtro_concepto:
        df_filtrado = df_filtrado[df_filtrado['Partida'].str.contains(filtro_concepto, case=False, na=False)]
    if filtro_destajista != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Destajista'] == filtro_destajista]
    if filtro_estado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Estado'] == filtro_estado]
    if fecha_filtro:
        df_filtrado = df_filtrado[df_filtrado['Fecha_Pago'] == str(fecha_filtro)]

    st.markdown("<br>", unsafe_allow_html=True)
    h1, h2, h3, h4, h5, h6 = st.columns([4, 1.5, 3, 1.5, 2, 1.5])
    h1.markdown("🗑️ **Partida**")
    h2.markdown("💵 **Costo**")
    h3.markdown("👷 **Destajista/Contratista**")
    h4.markdown("📊 **Estado**")
    h5.markdown("📆 **Fecha Pago**")
    h6.markdown("👤 **Usuario**")
    st.markdown("<hr style='margin:5px 0 15px 0;'>", unsafe_allow_html=True)
    
    with st.container(height=450):
        if df_filtrado.empty:
            st.info("No hay partidas que coincidan con los filtros seleccionados.")
        else:
            for numero, (indice, fila) in enumerate(df_filtrado.iterrows(), start=1):
                c1, c2, c3, c4, c5, c6 = st.columns([4, 1.5, 3, 1.5, 2, 1.5])
                
                # 2. Control total de los márgenes y letras inyectando HTML para achicar espacios
                c1.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA};'>{numero}.- {fila['Partida']}</div>", unsafe_allow_html=True)
                c2.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA};'>${fila['Precio']:,.2f}</div>", unsafe_allow_html=True)
                
                if fila['Estado'] == 'Pagado':
                    c3.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA};'>{fila['Destajista']}</div>", unsafe_allow_html=True)
                    # 4. Etiqueta personalizada delgada en lugar de la alerta gruesa de Streamlit
                    c4.markdown(f"<div style='background-color:#10B981; color:white; padding:{GROSOR_ETIQUETA_PAGADO}; border-radius:4px; font-size:{TAMANO_LETRA_PAGADO}; text-align:center; margin-bottom:{ESPACIO_ENTRE_RENGLONES};'>🔒 PAGADO</div>", unsafe_allow_html=True)
                    c5.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; font-size: {TAMANO_LETRA_TABLA};'>{fila['Fecha_Pago']}</div>", unsafe_allow_html=True)
                    user_val = fila['Usuario'] if pd.notna(fila['Usuario']) else ""
                    c6.markdown(f"<div style='font-size: {TAMANO_LETRA_TABLA}; text-align:center;'>{user_val}</div>", unsafe_allow_html=True)


                else:
                    destajista_seleccionado = c3.selectbox(
                        "Destajista Dropdown", 
                        options=["Seleccionar..."] + LISTA_DESTAJISTAS,
                        key=f"sel_{indice}", 
                        label_visibility="collapsed"
                    )
                    
                    if c4.button("P", key=f"btn_{indice}"):
                        if destajista_seleccionado == "Seleccionar...":
                            st.error("⚠️ Debes seleccionar un destajista primero.")
                        else:
                            dialogo_confirmacion(indice, fila['Lote'], fila['Partida'], destajista_seleccionado, fila['Precio'])
                    c5.markdown(f"<div style='margin-bottom: {ESPACIO_ENTRE_RENGLONES}; text-align: center;'>—</div>",
                     unsafe_allow_html=True)

# =========================================================================
# PESTAÑA 2: DASHBOARD
# =========================================================================
elif menu == "Dashboard (Gráficos y Visor)":
    st.title("📊 Visor Estadístico e Indicadores")
    
    def ordenar_prototipos(val):
        match = re.search(r"(\d+)(.*)", str(val))
        if match:
            num = int(match.group(1))
            texto = match.group(2)
            return (num, texto)
        return (float('inf'), str(val))

    st.markdown("### 🔍 Configuración de Evaluación")
    
    # 1. Filtros reubicados (Prototipo a la izquierda, Lote a la derecha) sin botón de "Seleccionar todos"
    d_col1, d_col2 = st.columns(2)
    protos_disponibles = sorted(df['Prototipo'].unique(), key=ordenar_prototipos)
    lotes_disponibles = df['Lote'].unique()
    
    # El usuario debe usar el menú desplegable (que ya incluye funcionalidad de selección múltiple)
    protos_dash = d_col1.multiselect("Filtrar por Prototipos:", options=protos_disponibles, default=protos_disponibles)
    lotes_dash = d_col2.multiselect("Filtrar por Lotes:", options=lotes_disponibles, default=lotes_disponibles)
    
    df_dash = df[(df['Lote'].isin(lotes_dash)) & (df['Prototipo'].isin(protos_dash))]
    
    if df_dash.empty:
        st.warning("⚠️ No hay datos para mostrar con los filtros seleccionados.")
    else:
        df_pagados = df_dash[df_dash['Estado'] == 'Pagado']
        df_pendientes = df_dash[df_dash['Estado'] != 'Pagado']
        
        monto_total = df_dash['Precio'].sum()
        monto_pagado = df_pagados['Precio'].sum()
        monto_pendiente = df_pendientes['Precio'].sum()
        
        # 2. Indicadores con formato forzado a dos decimales (.00)
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("💰 Valor Total de Selección", f"${monto_total:,.2f}")
        
        if monto_total > 0:
            pct_pagado = (monto_pagado / monto_total) * 100
            pct_pendiente = (monto_pendiente / monto_total) * 100
        else:
            pct_pagado, pct_pendiente = 0, 0
            
        kpi2.metric("✅ Total Ejercido / Pagado", f"${monto_pagado:,.2f}", f"{pct_pagado:.2f}%")
        kpi3.metric("⏳ Por Pagar (Deuda)", f"${monto_pendiente:,.2f}", f"-{pct_pendiente:.2f}%", delta_color="inverse")
        
        st.markdown("<hr>", unsafe_allow_html=True)
        
        st.markdown("### 📋 Resumen Individual por Lote y Prototipo")
        
        # 3. Agregamos Destajista a la agrupación y reordenamos columnas
        # Llenamos vacíos en Destajista para evitar errores de agrupación
        df_dash_clean = df_dash.copy()
        df_dash_clean['Destajista'] = df_dash_clean['Destajista'].fillna('Sin Asignar')
        
        df_resumen = df_dash_clean.groupby(['Lote', 'Prototipo', 'Destajista', 'Estado'])['Precio'].sum().unstack(fill_value=0).reset_index()
        
        if 'Pagado' not in df_resumen.columns: df_resumen['Pagado'] = 0.0
        if 'Pendiente' not in df_resumen.columns: df_resumen['Pendiente'] = 0.0
        
        df_resumen['Total'] = df_resumen['Pagado'] + df_resumen['Pendiente']
        
        # Reordenamos exactamente como pediste
        df_resumen = df_resumen[['Lote', 'Prototipo', 'Destajista', 'Total', 'Pagado', 'Pendiente']]
        df_resumen.columns = ['Lote', 'Prototipo', 'Destajista', 'Valor Total', 'Total Pagado', 'Deuda Pendiente']
        
        # Ocultamos el índice al mostrar el dataframe
        st.dataframe(
            df_resumen.style.format({
                'Valor Total': '${:,.2f}',
                'Total Pagado': '${:,.2f}',
                'Deuda Pendiente': '${:,.2f}'
            }), 
            use_container_width=True,
            hide_index=True
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # Gráficos (se mantienen igual, son excelentes)
        g_col1, g_col2 = st.columns(2)
        
        df_proto_graf = df_dash.groupby(['Prototipo', 'Estado'])['Precio'].sum().reset_index()
        fig_proto = px.bar(df_proto_graf, x='Prototipo', y='Precio', color='Estado', 
                           title="💼 Consolidado Financiero por Prototipo",
                           barmode='group', color_discrete_map={'Pagado': '#10B981', 'Pendiente': '#EF4444'})
        g_col1.plotly_chart(fig_proto, use_container_width=True)
        
        df_lotes_graf = df_dash.groupby(['Lote', 'Estado'])['Precio'].sum().reset_index()
        fig_lote = px.bar(df_lotes_graf, x='Lote', y='Precio', color='Estado', 
                          title="🏘️ Avance Financiero por Lote",
                          color_discrete_map={'Pagado': '#10B981', 'Pendiente': '#F59E0B'})
        g_col2.plotly_chart(fig_lote, use_container_width=True)

        g_col3, g_col4 = st.columns(2)
        
        if not df_pagados.empty:
            df_dest = df_pagados.groupby('Destajista')['Precio'].sum().reset_index()
            fig_dest = px.pie(df_dest, names='Destajista', values='Precio', 
                              title="👷 Pagos Ejecutados por Destajista",
                              hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
            g_col3.plotly_chart(fig_dest, use_container_width=True)
        else:
            g_col3.info("Aún no hay pagos ejecutados en la selección actual.")
            
        if not df_pendientes.empty:
            df_partidas_pend = df_pendientes.groupby('Partida')['Precio'].sum().reset_index()
            fig_part_pend = px.bar(df_partidas_pend, y='Partida', x='Precio', orientation='h', 
                                   title="📋 Presupuesto Pendiente por Partida", 
                                   color_discrete_sequence=['#3B82F6'])
            g_col4.plotly_chart(fig_part_pend, use_container_width=True)

# =========================================================================
# PESTAÑA 3: MAPA INTERACTIVO
# =========================================================================
elif menu == "Mapa Interactivo":
    st.title("🗺️ Plano de Lotes y Partidas de Obra")
    st.write("Tu archivo SVG se integrará en esta sección para pintar los cuadrados correspondientes a cada partida.")
