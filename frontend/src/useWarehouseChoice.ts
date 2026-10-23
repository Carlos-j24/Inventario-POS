import { useEffect, useState } from "react";

import { api, type Warehouse } from "./api";
import { useAuth } from "./auth";
import { proposeWarehouse, rememberedWarehouse, rememberWarehouse } from "./warehouse";

/**
 * Bodegas activas y la elegida en Entradas, Ajustes y Conteos (spec 008): propone la última que eligió
 * el usuario en este equipo o la principal, y recuerda lo que elige.
 */
export function useWarehouseChoice(onError: (message: string) => void) {
  const { user, loading } = useAuth();
  const username = user?.username;
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [warehouse, setWarehouse] = useState<number | null>(null);

  useEffect(() => {
    api<Warehouse[]>("/api/inventory/warehouses/").then(setWarehouses).catch((e: Error) => onError(e.message));
  }, []); // onError cambia en cada render de la pantalla: las bodegas se cargan una sola vez

  // Se propone cuando ya se sabe quién es: si no, se quedaría la principal en vez de la que recuerda este usuario.
  useEffect(() => {
    if (warehouses.length && !loading) setWarehouse((current) => current ?? proposeWarehouse(warehouses, rememberedWarehouse(username)));
  }, [warehouses, loading, username]);

  function choose(id: number) {
    setWarehouse(id);
    rememberWarehouse(username, id);
  }

  return { warehouses, warehouse, choose };
}
