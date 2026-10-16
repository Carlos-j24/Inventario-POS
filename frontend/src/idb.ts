// IndexedDB mínimo, sin librerías: un almacén clave-valor ("kv") para el catálogo y lo que
// la caja necesita sin red, y la cola de ventas pendientes ("outbox").

const DB_NAME = "inventario-pos";
const VERSION = 1;

let dbPromise: Promise<IDBDatabase> | null = null;

function open(): Promise<IDBDatabase> {
  dbPromise ??= new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("kv")) db.createObjectStore("kv");
      if (!db.objectStoreNames.contains("outbox")) db.createObjectStore("outbox", { keyPath: "client_uuid" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function run<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest): Promise<T> {
  return open().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const tx = db.transaction(store, mode);
        const req = fn(tx.objectStore(store));
        tx.oncomplete = () => resolve(req.result as T);
        tx.onerror = () => reject(tx.error);
      }),
  );
}

export const kv = {
  get: <T>(key: string) => run<T | undefined>("kv", "readonly", (s) => s.get(key)),
  set: (key: string, value: unknown) => run<void>("kv", "readwrite", (s) => s.put(value, key)),
  remove: (key: string) => run<void>("kv", "readwrite", (s) => s.delete(key)),
};

export const outboxDb = {
  all: <T>() => run<T[]>("outbox", "readonly", (s) => s.getAll()),
  put: (item: unknown) => run<void>("outbox", "readwrite", (s) => s.put(item)),
  remove: (id: string) => run<void>("outbox", "readwrite", (s) => s.delete(id)),
};
