
def get_product_gid_by_handle(handle):
    query = """
    {
      products(first: 1, query: \"handle:%s\") {
        edges {
          node {
            id
          }
        }
      }
    }
    """ % handle

    response = requests.post(
        f"https://{SHOP_URL}/admin/api/2023-07/graphql.json",
        headers={
            'X-Shopify-Access-Token': ACCESS_TOKEN,
            'Content-Type': 'application/json'
        },
        json={'query': query}
    )

    try:
        edges = response.json().get("data", {}).get("products", {}).get("edges", [])
        if edges:
            return edges[0]['node']['id']
    except Exception as e:
        print(f"❌ Erro ao obter GID do produto {handle}: {e}")
    return None

def update_metafield_specifications(product_gid, specifications):
    mutation = """
    mutation ProductUpdate($input: ProductInput!) {
      productUpdate(input: $input) {
        product {
          id
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "id": product_gid,
            "metafields": [
                {
                    "namespace": "custom",
                    "key": "especifica_es_t_cnicas",
                    "type": "multi_line_text_field",
                    "value": specifications.strip()
                }
            ]
        }
    }

    response = requests.post(
        f"https://{SHOP_URL}/admin/api/2023-07/graphql.json",
        headers={
            'X-Shopify-Access-Token': ACCESS_TOKEN,
            'Content-Type': 'application/json'
        },
        json={"query": mutation, "variables": variables}
    )

    if response.status_code == 200:
        res_data = response.json()
        errors = res_data.get("data", {}).get("productUpdate", {}).get("userErrors", [])
        if errors:
            print(f"⚠️ Erros ao atualizar metafield: {errors}")
        else:
            print("✅ Metafield atualizado com sucesso.")
    else:
        print(f"❌ Erro HTTP ao atualizar metafield: {response.status_code}, {response.text}")
