import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import BrandLogo from "./BrandLogo";

describe("logo del negocio", () => {
  it("lo pide al servidor de la instalación", () => {
    render(<BrandLogo className="login-logo" alt="Logo del negocio" />);
    const logo = screen.getByRole("img", { name: "Logo del negocio" });
    expect(logo).toHaveAttribute("src", "/brand/logo.png");
    expect(logo).toHaveClass("login-logo");
  });

  it("si la instalación no trae logo, no muestra nada (ni la imagen rota)", () => {
    const { container } = render(<BrandLogo className="topbar-logo" />);
    fireEvent.error(container.querySelector("img")!);
    expect(container).toBeEmptyDOMElement();
  });
});
