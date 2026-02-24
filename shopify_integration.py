import os
import requests
from typing import List, Dict, Optional

# Shopify API uses store-specific credentials


def create_shopify_client(shop_name: str, access_token: str):
    """
    Create a Shopify API client
    
    Args:
        shop_name: Shopify store name (e.g., 'my-store' from my-store.myshopify.com)
        access_token: Shopify Admin API access token
    
    Returns:
        Base URL and headers for API requests
    """
    base_url = f"https://{shop_name}.myshopify.com/admin/api/2024-01"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    
    return base_url, headers


def get_products(shop_name: str, access_token: str, limit: int = 50) -> Dict:
    """
    Get list of products from Shopify store
    
    Returns:
        {
            "success": bool,
            "products": [
                {
                    "id": int,
                    "title": str,
                    "price": str,
                    "inventory_quantity": int,
                    "variants": [...]
                }
            ],
            "error": str (if failed)
        }
    """
    try:
        base_url, headers = create_shopify_client(shop_name, access_token)
        
        response = requests.get(
            f"{base_url}/products.json",
            headers=headers,
            params={"limit": limit, "status": "active"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            products = []
            
            for product in data.get("products", []):
                # Get first variant for price
                variant = product["variants"][0] if product.get("variants") else {}
                
                products.append({
                    "id": product["id"],
                    "title": product["title"],
                    "description": product.get("body_html", "")[:200],  # Truncate
                    "price": variant.get("price", "0"),
                    "inventory_quantity": variant.get("inventory_quantity", 0),
                    "variants": product.get("variants", []),
                    "image": product["images"][0]["src"] if product.get("images") else None
                })
            
            return {
                "success": True,
                "products": products,
                "count": len(products)
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_products(shop_name: str, access_token: str, query: str) -> Dict:
    """
    Search for products by name/description
    
    Args:
        shop_name: Shopify store name
        access_token: Admin API token
        query: Search query
    
    Returns:
        {"success": bool, "products": [...], "error": str}
    """
    try:
        base_url, headers = create_shopify_client(shop_name, access_token)
        
        response = requests.get(
            f"{base_url}/products.json",
            headers=headers,
            params={"title": query, "limit": 10},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            products = []
            
            for product in data.get("products", []):
                variant = product["variants"][0] if product.get("variants") else {}
                
                products.append({
                    "id": product["id"],
                    "title": product["title"],
                    "price": variant.get("price", "0"),
                    "inventory_quantity": variant.get("inventory_quantity", 0)
                })
            
            return {
                "success": True,
                "products": products
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}"
            }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_order(
    shop_name: str,
    access_token: str,
    customer_email: str,
    customer_name: str,
    customer_phone: str,
    line_items: List[Dict],
    shipping_address: Optional[Dict] = None,
    financial_status: str = "pending"
) -> Dict:
    """
    Create an order in Shopify
    
    Args:
        shop_name: Shopify store name
        access_token: Admin API token
        customer_email: Customer email
        customer_name: Customer full name
        customer_phone: Customer phone number
        line_items: [{"variant_id": int, "quantity": int, "price": str}]
        shipping_address: Optional shipping address dict
        financial_status: "pending", "paid", "authorized"
    
    Returns:
        {
            "success": bool,
            "order_id": int,
            "order_number": int,
            "total": str,
            "error": str (if failed)
        }
    """
    try:
        base_url, headers = create_shopify_client(shop_name, access_token)
        
        # Split name into first/last
        name_parts = customer_name.split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        
        # Build order payload
        order_data = {
            "order": {
                "line_items": line_items,
                "customer": {
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": customer_email,
                    "phone": customer_phone
                },
                "financial_status": financial_status,
                "send_receipt": True,
                "send_fulfillment_receipt": False,
                "note": "Order placed via phone call"
            }
        }
        
        # Add shipping address if provided
        if shipping_address:
            order_data["order"]["shipping_address"] = shipping_address
        
        response = requests.post(
            f"{base_url}/orders.json",
            headers=headers,
            json=order_data,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            order = data.get("order", {})
            
            return {
                "success": True,
                "order_id": order.get("id"),
                "order_number": order.get("order_number"),
                "total": order.get("total_price"),
                "order_name": order.get("name"),
                "currency": order.get("currency", "USD")
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_product_variants(shop_name: str, access_token: str, product_id: int) -> Dict:
    """
    Get all variants for a product (sizes, colors, etc.)
    
    Returns:
        {
            "success": bool,
            "variants": [
                {
                    "id": int,
                    "title": str,
                    "price": str,
                    "inventory_quantity": int
                }
            ]
        }
    """
    try:
        base_url, headers = create_shopify_client(shop_name, access_token)
        
        response = requests.get(
            f"{base_url}/products/{product_id}.json",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            product = data.get("product", {})
            
            variants = []
            for variant in product.get("variants", []):
                variants.append({
                    "id": variant["id"],
                    "title": variant.get("title", "Default"),
                    "price": variant.get("price", "0"),
                    "inventory_quantity": variant.get("inventory_quantity", 0),
                    "sku": variant.get("sku", "")
                })
            
            return {
                "success": True,
                "variants": variants,
                "product_title": product.get("title")
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}"
            }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_inventory(shop_name: str, access_token: str, variant_id: int) -> Dict:
    """
    Check inventory for a specific variant
    
    Returns:
        {
            "success": bool,
            "in_stock": bool,
            "quantity": int
        }
    """
    try:
        base_url, headers = create_shopify_client(shop_name, access_token)
        
        response = requests.get(
            f"{base_url}/variants/{variant_id}.json",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            variant = data.get("variant", {})
            
            quantity = variant.get("inventory_quantity", 0)
            
            return {
                "success": True,
                "in_stock": quantity > 0,
                "quantity": quantity,
                "price": variant.get("price", "0")
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}"
            }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_order_status(shop_name: str, access_token: str, order_id: int) -> Dict:
    """
    Get order status
    
    Returns:
        {
            "success": bool,
            "status": str,
            "financial_status": str,
            "fulfillment_status": str
        }
    """
    try:
        base_url, headers = create_shopify_client(shop_name, access_token)
        
        response = requests.get(
            f"{base_url}/orders/{order_id}.json",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            order = data.get("order", {})
            
            return {
                "success": True,
                "order_number": order.get("order_number"),
                "financial_status": order.get("financial_status"),
                "fulfillment_status": order.get("fulfillment_status"),
                "total": order.get("total_price"),
                "created_at": order.get("created_at")
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}"
            }
    
    except Exception as e:
        return {"success": False, "error": str(e)}
