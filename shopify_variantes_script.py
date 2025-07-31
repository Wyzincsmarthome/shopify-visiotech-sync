import pandas as pd
import requests
import json
import os
import re
import time

SHOP_URL = os.environ["SHOP_URL"]
ACCESS_TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]

SHOP_URL = config["shop_url"]
ACCESS_TOKEN = config["access_token"]
API_VERSION = "2023-07"

CSV_PATH = "csv-input/visiotech.csv"
MARCAS_PERMITIDAS = ["AJAX", "AJAXCCTV", "AJAXVIVIENDAVACÍA", "AQARA", "REOLINK", "YALE"]
CATEGORIAS_EXCLUIDAS = set(map(lambda s: str(s).strip().lower(), [
    "Armazenamento em nuvem Ajax", "Outlet", "Peças de reposição"
]))

SKUS_EXCLUIDOS = [
    "AJ-BATTERYKIT-12M", "4823114061363", "4823114036996", "4823114036989",
    "4823114015038", "4823114066863", "4823114015021", "4823114027789",
    "4823114069956", "4823114053474", "4823114053481", "4823114015243",
    "8435325493091", "AJ-SITEGUARD-CHARGER", "AJ-SITEGUARD-W", "AJ-SITEGUARD-Y",
    "4823114007316", "4823114065125", "4823114015489", "4823114015472"
]

CORES_VALIDAS = ["W", "B", "BLK", "WHITE", "BLACK", "BRANCO", "PRETO",
                 "OLI", "GRE", "FOG", "GRA", "OYS", "IVO"]

# === Funções ===
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
    preco_final = round((preco_venda + 7) * 1.23, 2)
    return preco_final

def obter_produtos_shopify():
    headers = {"X-Shopify-Access-Token": ACCESS_TOKEN}
    url = f"https://{SHOP_URL}/admin/api/{API_VERSION}/products.json?limit=250"
    response = requests.get(url, headers=headers)
    return response.json().get("products", []) if response.status_code == 200 else []

def extrair_modelo_base(sku):
    partes = sku.upper().split("-")
    modelo = [p for p in partes if p not in CORES_VALIDAS]
    return "-".join(modelo)

def atualizar_variantes_existentes(produto_shopify, grupo):
    headers = {
        "X-Shopify-Access-Token": ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    for _, row in grupo.iterrows():
        ean = str(row["ean"]).strip()
        if pd.isna(ean) or ean.lower() == "nan":
            ean = ""
        if row["name"] in SKUS_EXCLUIDOS or ean in SKUS_EXCLUIDOS:
            continue

        sku = ean if ean else row["name"]
        stock = convert_stock(row["stock"])
        preco_custo = float(row["precio_neto_compra"])
        preco_venda = aplicar_iva_e_transporte(preco_custo)

        for variante in produto_shopify.get("variants", []):
            if variante.get("sku") == sku:
                variant_data = {
                    "variant": {
                        "id": variante["id"],
                        "price": preco_venda,
                        "inventory_quantity": stock
                    }
                }
                url = f"https://{SHOP_URL}/admin/api/{API_VERSION}/variants/{variante['id']}.json"
                response = requests.put(url, headers=headers, data=json.dumps(variant_data))

                if response.status_code in [200, 201]:
                    print(f"✔ Variante atualizada: {sku}")
                else:
                    print(f"❌ Erro ({response.status_code}) ao atualizar variante {sku}: {response.text}")
                break

def criar_produtos_com_variantes(df):
    produtos_shopify = obter_produtos_shopify()
    produtos_existentes = {p['handle']: p for p in produtos_shopify}

    df["modelo_base"] = df["name"].apply(extrair_modelo_base)
    agrupados = df.groupby("modelo_base")

    for modelo_base, grupo in agrupados:
        handle = modelo_base.lower()

        grupo = grupo.copy()
        grupo["ean"] = grupo["ean"].astype(str).str.strip()
        grupo = grupo[~grupo["name"].isin(SKUS_EXCLUIDOS)]
        grupo = grupo[~grupo["ean"].isin(SKUS_EXCLUIDOS)]

        if grupo.empty:
            continue

        if handle in produtos_existentes:
            atualizar_variantes_existentes(produtos_existentes[handle], grupo)
            continue

        if len(grupo) > 1:
            tem_variantes = True
        else:
            tem_variantes = False

        variantes = []
        imagens = []
        nome_produto = grupo.iloc[0]["short_description"][:255]
        descricao = grupo.iloc[0]["description"]
        marca_original = grupo.iloc[0]["brand"]
        marca = "Ajax" if marca_original.upper() in ["AJAX", "AJAXCCTV", "AJAXVIVIENDAVACÍA"] else marca_original
        tipo = grupo.iloc[0]["category"]

        grupo_sorted = sorted(grupo.iterrows(), key=lambda r: json.loads(r[1]["params"]).get("color", "zzzzzz").lower() != "branco")

        for _, row in grupo_sorted:
            ean = str(row["ean"]).strip()
            if pd.isna(ean) or ean.lower() == "nan":
                ean = ""
            sku = ean if ean else row["name"]
            stock = convert_stock(row["stock"])
            preco_custo = float(row["precio_neto_compra"])
            preco_venda = aplicar_iva_e_transporte(preco_custo)
            imagem_principal = row["image_path"]

            try:
                imagens_extra = json.loads(row["extra_images_paths"]).get("details", [])
            except:
                imagens_extra = []

            try:
                params = json.loads(row["params"])
                cor = params.get("color", "").strip().capitalize()
            except:
                cor = ""

            variante_data = {
                "sku": sku,
                "barcode": ean,
                "price": preco_venda,
                "inventory_quantity": stock,
                "inventory_management": "shopify",
                "cost": preco_custo
            }

            if tem_variantes:
                variante_data["option1"] = cor or "Padrão"

            variantes.append(variante_data)
            imagens.append({"src": imagem_principal})
            for img in imagens_extra:
                imagens.append({"src": img})

        if not variantes:
            continue

        descricao_final = f"{descricao}<br><br><strong>Marca:</strong> {marca}<br><strong>Categoria:</strong> {tipo}"

        produto_payload = {
            "product": {
                "title": nome_produto,
                "body_html": descricao_final,
                "vendor": marca,
                "product_type": tipo,
                "tags": marca,
                "handle": handle,
                "images": imagens,
                "variants": variantes
            }
        }

        if tem_variantes:
            produto_payload["product"]["options"] = [{"name": "Cor"}]

        headers = {
            "X-Shopify-Access-Token": ACCESS_TOKEN,
            "Content-Type": "application/json"
        }

        url = f"https://{SHOP_URL}/admin/api/{API_VERSION}/products.json"
        response = requests.post(url, headers=headers, data=json.dumps(produto_payload))

        if response.status_code in [200, 201]:
            print(f"✔ Produto criado: {handle}")
        else:
            print(f"❌ Erro ({response.status_code}) ao criar {handle}: {response.text}")

if __name__ == "__main__":
    if not os.path.exists(CSV_PATH):
        print(f"❌ Ficheiro CSV não encontrado: {CSV_PATH}")
        exit()

    df = pd.read_csv(CSV_PATH, sep=";", encoding="latin1", low_memory=False)
    df = df[df["brand"].str.upper().isin(MARCAS_PERMITIDAS)]
    df = df[~df["category"].apply(lambda s: str(s).strip().lower()).isin(CATEGORIAS_EXCLUIDAS)]
    criar_produtos_com_variantes(df)
