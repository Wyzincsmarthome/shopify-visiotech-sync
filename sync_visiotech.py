import pandas as pd
import requests
import json
import os
import re

with open("shopify_config.json") as f:
    config = json.load(f)

SHOP_URL = config["shop_url"]
ACCESS_TOKEN = config["access_token"]
API_VERSION = "2023-07"

CSV_PATH = "csv-input/visiotech.csv"
MARCAS_PERMITIDAS = ["AJAX", "AJAXCCTV", "AJAXVIVIENDAVACÍA", "AQARA", "REOLINK", "YALE"]
CATEGORIAS_EXCLUIDAS = ["Armazenamento em nuvem Ajax", "Outlet", "Peças de reposição"]
SKUS_EXCLUIDOS = [
    "AJ-BATTERYKIT-12M", "4823114061363", "4823114036996", "4823114036989",
    "4823114015038", "4823114066863", "4823114015021", "4823114027789",
    "4823114069956", "4823114053474", "4823114053481", "4823114015243",
    "8435325493091", "AJ-SITEGUARD-CHARGER", "AJ-SITEGUARD-W", "AJ-SITEGUARD-Y",
    "4823114007316", "4823114065125", "4823114015489", "4823114015472"
]

def convert_stock(value):
    return {"high": 10, "medium": 5, "low": 2, "none": 0}.get(str(value).strip().lower(), 0)

def aplicar_iva_e_transporte(preco_custo):
    if preco_custo <= 10:
        margem = 0.6
    elif preco_custo <= 20:
        margem = 0.5
    elif preco_custo <= 40:
        margem = 0.4
    elif preco_custo <= 80:
        margem = 0.3
    else:
        margem = 0.25
    preco_venda = preco_custo * (1 + margem)
    preco_final = round(preco_venda * 1.23 + 7, 2)
    return preco_final

def obter_produtos_shopify():
    headers = {"X-Shopify-Access-Token": ACCESS_TOKEN}
    url = f"https://{SHOP_URL}/admin/api/{API_VERSION}/products.json?limit=250"
    response = requests.get(url, headers=headers)
    return response.json().get("products", []) if response.status_code == 200 else []

def extrair_modelo_base(sku):
    return "-".join(sku.split("-")[:-1]) if "-" in sku else sku

def criar_produtos_com_variantes(df):
    produtos_shopify = obter_produtos_shopify()
    handles_existentes = {p["handle"] for p in produtos_shopify}

    grupos = df.groupby(df["name"].apply(extrair_modelo_base))

    for modelo, grupo in grupos:
        if any(sku in SKUS_EXCLUIDOS for sku in grupo["name"]):
            continue

        primeira = grupo.iloc[0]
        nome = primeira["short_description"]
        descricao = primeira["description"]
        especificacoes = primeira["specifications"] if pd.notna(primeira["specifications"]) else ""
        descricao_final = f"{descricao}<br><br><strong>Especificações Técnicas:</strong><br>{especificacoes}"
        marca_original = primeira["brand"]
        marca = "Ajax" if marca_original.upper() in ["AJAX", "AJAXCCTV", "AJAXVIVIENDAVACÍA"] else marca_original
        tipo = primeira["category"] if pd.notna(primeira["category"]) else marca

        imagens_extra = []
        try:
            imagens_extra = json.loads(primeira["extra_images_paths"]).get("details", [])
        except:
            pass

        variantes = []
        imagens_produto = []

        for _, row in grupo.iterrows():
            ean = row["ean"] if pd.notna(row["ean"]) else ""
            sku = ean if ean else row["name"]
            stock = convert_stock(row["stock"])
            preco_custo = float(row["precio_neto_compra"])
            preco_venda = aplicar_iva_e_transporte(preco_custo)
            imagem_principal = row["image_path"]

            cor = "Cor desconhecida"
            try:
                params = json.loads(row["params"])
                cor = params.get("color", "Cor desconhecida")
            except:
                pass

            variantes.append({
                "sku": sku,
                "barcode": ean if ean else "",
                "price": preco_venda,
                "inventory_quantity": stock,
                "inventory_management": "shopify",
                "option1": cor,
                "cost": preco_custo,
                "image": {"src": imagem_principal}
            })

            imagens_produto.append({"src": imagem_principal})

        if modelo.lower() in handles_existentes:
            print(f"⚠ Produto já existe: {modelo}, a atualização não é feita neste script.")
            continue

        if len(variantes) == 1:
            variante_unica = variantes[0]
            dados_produto = {
                "product": {
                    "title": nome,
                    "body_html": descricao_final,
                    "vendor": marca,
                    "product_type": tipo,
                    "tags": marca,
                    "handle": modelo.lower(),
                    "images": imagens_produto + [{"src": img} for img in imagens_extra],
                    "variants": [variante_unica]
                }
            }
        else:
            dados_produto = {
                "product": {
                    "title": nome,
                    "body_html": descricao_final,
                    "vendor": marca,
                    "product_type": tipo,
                    "tags": marca,
                    "handle": modelo.lower(),
                    "images": imagens_produto + [{"src": img} for img in imagens_extra],
                    "options": [{"name": "Cor"}],
                    "variants": variantes
                }
            }

        headers = {
            "X-Shopify-Access-Token": ACCESS_TOKEN,
            "Content-Type": "application/json"
        }

        url = f"https://{SHOP_URL}/admin/api/{API_VERSION}/products.json"
        response = requests.post(url, headers=headers, data=json.dumps(dados_produto))

        if response.status_code in [200, 201]:
            print(f"✔ Produto criado com sucesso: {modelo}")
        else:
            print(f"❌ Erro ({response.status_code}) ao criar {modelo}: {response.text}")

if __name__ == "__main__":
    if not os.path.exists(CSV_PATH):
        print(f"❌ Ficheiro CSV não encontrado: {CSV_PATH}")
        exit()

    df = pd.read_csv(CSV_PATH, sep=";", encoding="latin1", low_memory=False)
    df = df[df["brand"].str.upper().isin(MARCAS_PERMITIDAS)]
    df = df[~df["category"].isin(CATEGORIAS_EXCLUIDAS)]

    criar_produtos_com_variantes(df)
