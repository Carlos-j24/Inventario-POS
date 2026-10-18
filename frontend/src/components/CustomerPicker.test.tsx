import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Customer } from "../api";
import CustomerPicker from "./CustomerPicker";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const customer = (over: Partial<Customer> = {}): Customer => ({
  id: 5, id_type: "31", id_type_label: "NIT", id_number: "800197268", check_digit: "4", person_type: "1",
  name: "Constructora SAS", email: "compras@ejemplo.co", phone: "", address: "", city: "", tax_responsibilities: [],
  is_final_consumer: false, ...over,
});

function mockApi(handler: (url: string, init?: RequestInit) => Response | undefined) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const res = handler(url, init);
    return res ? Promise.resolve(res) : Promise.reject(new Error(`ruta no simulada: ${url}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

function Harness({ onChange }: { onChange: (c: Customer | null) => void }) {
  const [value, setValue] = useState<Customer | null>(null);
  return <CustomerPicker value={value} onChange={(c) => { setValue(c); onChange(c); }} />;
}

describe("cliente en la caja", () => {
  it("por defecto es el consumidor final; busca y elige un cliente", async () => {
    const fetch = mockApi((url) =>
      url === "/api/customers/?q=800" ? json([customer(), customer({ id: 1, name: "Consumidor final", is_final_consumer: true })]) : undefined,
    );
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    expect(screen.getByText("Consumidor final")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Identificar cliente" }));
    await userEvent.type(screen.getByLabelText("Buscar cliente"), "8");
    await new Promise((r) => setTimeout(r, 350));
    expect(fetch).not.toHaveBeenCalled(); // con un solo carácter no busca
    await userEvent.type(screen.getByLabelText("Buscar cliente"), "00");
    await screen.findByRole("button", { name: /Constructora SAS/ });
    expect(screen.getAllByRole("listitem")).toHaveLength(1); // el consumidor final no se ofrece en la búsqueda
    await userEvent.click(screen.getByRole("button", { name: /Constructora SAS/ }));
    expect(onChange).toHaveBeenLastCalledWith(customer());
    expect(screen.getByText(/NIT 800197268-4/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: "Consumidor final" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("registra un cliente nuevo con el número que se buscaba", async () => {
    const created = customer({ id: 9, id_type: "13", id_type_label: "Cédula", id_number: "1020304050", check_digit: "", person_type: "2", name: "Ana Gómez", email: "" });
    const fetch = mockApi((url, init) => {
      if (url.startsWith("/api/customers/?q=")) return json([]);
      if (url === "/api/customers/" && init?.method === "POST") return json(created, 201);
    });
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Identificar cliente" }));
    await userEvent.type(screen.getByLabelText("Buscar cliente"), "1020304050");
    await userEvent.click(screen.getByRole("button", { name: "Nuevo cliente" }));
    expect(screen.getByLabelText("Número de documento")).toHaveValue("1020304050");
    const save = screen.getByRole("button", { name: "Guardar cliente" });
    expect(save).toBeDisabled(); // falta el nombre
    expect(screen.queryByLabelText(/persona jurídica/)).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Nombre o razón social"), "Ana Gómez");
    await userEvent.click(save);
    expect(onChange).toHaveBeenLastCalledWith(created);
    const post = fetch.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(JSON.parse((post[1] as RequestInit).body as string)).toEqual({ id_type: "13", id_number: "1020304050", name: "Ana Gómez", email: "", person_type: "2" });
  });

  it("una empresa con NIT es persona jurídica, y los errores del servidor se muestran", async () => {
    const fetch = mockApi((url, init) => {
      if (url.startsWith("/api/customers/?q=")) return json([]);
      if (init?.method === "POST") return json({ check_digit: ["El dígito de verificación de este NIT es 4."] }, 400);
    });
    render(<Harness onChange={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Identificar cliente" }));
    await userEvent.click(screen.getByRole("button", { name: "Nuevo cliente" }));
    await userEvent.selectOptions(screen.getByLabelText("Tipo de documento"), "31");
    await userEvent.type(screen.getByLabelText("Número de documento"), "800197268");
    await userEvent.type(screen.getByLabelText("Nombre o razón social"), "Constructora SAS");
    await userEvent.click(screen.getByLabelText(/persona jurídica/));
    await userEvent.click(screen.getByRole("button", { name: "Guardar cliente" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("es 4");
    const post = fetch.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(JSON.parse((post[1] as RequestInit).body as string).person_type).toBe("1");
  });

  it("si marca empresa y luego cambia a cédula, queda como persona natural", async () => {
    const fetch = mockApi((url, init) => {
      if (url.startsWith("/api/customers/?q=")) return json([]);
      if (init?.method === "POST") return json(customer(), 201);
    });
    render(<Harness onChange={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Identificar cliente" }));
    await userEvent.click(screen.getByRole("button", { name: "Nuevo cliente" }));
    await userEvent.selectOptions(screen.getByLabelText("Tipo de documento"), "31");
    await userEvent.click(screen.getByLabelText(/persona jurídica/));
    await userEvent.selectOptions(screen.getByLabelText("Tipo de documento"), "13");
    await userEvent.type(screen.getByLabelText("Número de documento"), "1020");
    await userEvent.type(screen.getByLabelText("Nombre o razón social"), "Ana");
    await userEvent.click(screen.getByRole("button", { name: "Guardar cliente" }));
    const post = fetch.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(JSON.parse((post[1] as RequestInit).body as string).person_type).toBe("2");
  });
});
