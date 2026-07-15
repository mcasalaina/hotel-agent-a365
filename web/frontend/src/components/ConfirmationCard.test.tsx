import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConfirmationCard } from "./ConfirmationCard";
import type { ConfirmationEntry } from "../hooks/callSessionReducer";

const baseConfirmation: ConfirmationEntry = {
  id: "entry-1",
  confirmationId: "confirmation-1",
  summary: "Change room type to Deluxe Suite?",
  details: { Guest: "Jordan Ellery (synthetic)", Room: "Deluxe Suite" },
  timestamp: "t1",
  resolvedApproved: null,
};

describe("ConfirmationCard", () => {
  it("renders the summary and detail fields", () => {
    render(<ConfirmationCard confirmation={baseConfirmation} onRespond={vi.fn()} />);
    expect(screen.getByText(/change room type to deluxe suite/i)).toBeInTheDocument();
    expect(screen.getByText("Jordan Ellery (synthetic)")).toBeInTheDocument();
    expect(screen.getByText("Deluxe Suite")).toBeInTheDocument();
  });

  it("calls onRespond with the confirmation id and approval when Approve is pressed", async () => {
    const onRespond = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmationCard confirmation={baseConfirmation} onRespond={onRespond} />);

    await user.click(screen.getByRole("button", { name: /approve/i }));
    expect(onRespond).toHaveBeenCalledWith("confirmation-1", true);
  });

  it("calls onRespond with approved=false when Decline is pressed", async () => {
    const onRespond = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmationCard confirmation={baseConfirmation} onRespond={onRespond} />);

    await user.click(screen.getByRole("button", { name: /decline/i }));
    expect(onRespond).toHaveBeenCalledWith("confirmation-1", false);
  });

  it("shows a resolved note instead of action buttons once approved", () => {
    render(
      <ConfirmationCard
        confirmation={{ ...baseConfirmation, resolvedApproved: true }}
        onRespond={vi.fn()}
      />,
    );
    expect(screen.getByText(/you approved this change/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  });
});
