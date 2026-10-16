import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { promptInstall, useCanInstall } from "./install";

function Button() {
  const canInstall = useCanInstall();
  return canInstall ? <button onClick={() => promptInstall()}>Instalar app</button> : <p>No instalable</p>;
}

function fakePrompt(outcome: "accepted" | "dismissed") {
  const event = new Event("beforeinstallprompt", { cancelable: true }) as Event & {
    prompt: ReturnType<typeof vi.fn>;
    userChoice: Promise<{ outcome: string }>;
  };
  event.prompt = vi.fn().mockResolvedValue(undefined);
  event.userChoice = Promise.resolve({ outcome });
  return event;
}

describe("botón Instalar app", () => {
  it("aparece cuando el navegador avisa, abre su cuadro y desaparece (el aviso sirve una sola vez)", async () => {
    render(<Button />);
    expect(screen.getByText("No instalable")).toBeInTheDocument();

    const event = fakePrompt("accepted");
    act(() => void window.dispatchEvent(event));
    expect(event.defaultPrevented).toBe(true); // Chrome no muestra su propio aviso
    await userEvent.click(screen.getByRole("button", { name: "Instalar app" }));

    expect(event.prompt).toHaveBeenCalledTimes(1);
    expect(screen.getByText("No instalable")).toBeInTheDocument();
  });

  it("desaparece si la app se instala desde el menú del navegador", () => {
    render(<Button />);
    act(() => void window.dispatchEvent(fakePrompt("dismissed")));
    expect(screen.getByRole("button", { name: "Instalar app" })).toBeInTheDocument();
    act(() => void window.dispatchEvent(new Event("appinstalled")));
    expect(screen.getByText("No instalable")).toBeInTheDocument();
  });

  it("promptInstall sin aviso del navegador no hace nada", async () => {
    expect(await promptInstall()).toBe(false);
  });
});
