import streamlit as st
from PIL import Image
import os

def configurar_interface_ifi():

    # 2. CSS Customizado (Mantido)
    st.markdown("""
        <style>
            /* Cor dos Títulos Principais */
            h1, h2, h3 {
                color: #003366 !important;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            
            /* Estilização dos Cards de Métricas (Metrics) */
            [data-testid="stMetric"] {
                background-color: #f8f9fa;
                padding: 15px;
                border-radius: 10px;
                border-left: 5px solid #003366;
                box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
            }

            /* Ajuste na barra lateral */
            [data-testid="stSidebar"] {
                background-color: #f0f2f6;
            }

            /* Botões de Download e Outros */
            .stButton>button {
                border-radius: 5px;
                border: 1px solid #003366;
                color: #003366;
            }
            
            .stButton>button:hover {
                background-color: #003366;
                color: white;
            }
        </style>
    """, unsafe_allow_html=True)

# Paleta de cores oficial para usar nos gráficos Plotly
CORES_IFI = ["#003366", "#006699", "#FF9900", "#666666", "#99BADD"]