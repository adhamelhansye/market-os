import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

export type Product = components["schemas"]["ProductRead"];
export type ProductDetail = components["schemas"]["ProductDetailRead"];
export type ProductCreate = components["schemas"]["ProductCreate"];
export type ProductUpdate = components["schemas"]["ProductUpdate"];
export type ProductPrice = components["schemas"]["ProductPriceRead"];
export type ProductPriceCreate = components["schemas"]["ProductPriceCreate"];
export type ProductCost = components["schemas"]["ProductCostRead"];
export type ProductCostCreate = components["schemas"]["ProductCostCreate"];
export type Inventory = components["schemas"]["InventoryRead"];

export function fetchProducts(businessId: string): Promise<ProductDetail[]> {
  return apiGet<ProductDetail[]>(`/api/v1/businesses/${businessId}/products`);
}

export function fetchProduct(businessId: string, productId: string): Promise<Product> {
  return apiGet<Product>(`/api/v1/businesses/${businessId}/products/${productId}`);
}

export function createProduct(
  businessId: string,
  payload: ProductCreate
): Promise<Product> {
  return apiPost<Product>(`/api/v1/businesses/${businessId}/products`, payload);
}

export function updateProduct(
  businessId: string,
  productId: string,
  payload: ProductUpdate
): Promise<Product> {
  return apiPatch<Product>(
    `/api/v1/businesses/${businessId}/products/${productId}`,
    payload
  );
}

export function archiveProduct(businessId: string, productId: string): Promise<void> {
  return apiDelete<void>(`/api/v1/businesses/${businessId}/products/${productId}`);
}

export function fetchPrices(
  businessId: string,
  productId: string
): Promise<ProductPrice[]> {
  return apiGet<ProductPrice[]>(
    `/api/v1/businesses/${businessId}/products/${productId}/prices`
  );
}

export function createPrice(
  businessId: string,
  productId: string,
  payload: ProductPriceCreate
): Promise<ProductPrice> {
  return apiPost<ProductPrice>(
    `/api/v1/businesses/${businessId}/products/${productId}/prices`,
    payload
  );
}

export function fetchCosts(
  businessId: string,
  productId: string
): Promise<ProductCost[]> {
  return apiGet<ProductCost[]>(
    `/api/v1/businesses/${businessId}/products/${productId}/costs`
  );
}

export function createCost(
  businessId: string,
  productId: string,
  payload: ProductCostCreate
): Promise<ProductCost> {
  return apiPost<ProductCost>(
    `/api/v1/businesses/${businessId}/products/${productId}/costs`,
    payload
  );
}

export function fetchInventory(
  businessId: string,
  productId: string
): Promise<Inventory> {
  return apiGet<Inventory>(
    `/api/v1/businesses/${businessId}/products/${productId}/inventory`
  );
}

export function setInventory(
  businessId: string,
  productId: string,
  quantity: number
): Promise<Inventory> {
  return apiPut<Inventory>(
    `/api/v1/businesses/${businessId}/products/${productId}/inventory`,
    { quantity }
  );
}

export function adjustInventory(
  businessId: string,
  productId: string,
  quantityDelta: number
): Promise<Inventory> {
  return apiPatch<Inventory>(
    `/api/v1/businesses/${businessId}/products/${productId}/inventory`,
    { quantity_delta: quantityDelta }
  );
}