import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import FieldRow from "../components/FieldRow.jsx";

function makeListing(overrides = {}) {
  return {
    id: 1,
    edited_fields: {},
    price_gbp: null,
    chain_free: null,
    address: null,
    ...overrides,
  };
}

describe("FieldRow display formatting", () => {
  it("shows an em dash for null/undefined/empty values", () => {
    render(<FieldRow listing={makeListing()} field="address" label="Address" />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("formats boolean fields as Yes/No", () => {
    render(<FieldRow listing={makeListing({ chain_free: true })} field="chain_free" label="Chain free" boolean />);
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("formats currency fields with a £ prefix", () => {
    render(<FieldRow listing={makeListing({ price_gbp: 475000 })} field="price_gbp" label="Price" currency />);
    expect(screen.getByText("£475000")).toBeInTheDocument();
  });

  it("shows an 'edited by you' badge when the field is sticky", () => {
    render(
      <FieldRow
        listing={makeListing({ price_gbp: 600000, edited_fields: { price_gbp: "2026-01-01" } })}
        field="price_gbp"
        label="Price"
        currency
      />
    );
    expect(screen.getByText("edited by you")).toBeInTheDocument();
  });

  it("shows a source badge when not edited and a source is set", () => {
    render(
      <FieldRow
        listing={makeListing({ council_tax_band: "D", council_tax_band_source: "rightmove" })}
        field="council_tax_band"
        label="Council tax band"
        sourceField="council_tax_band_source"
      />
    );
    expect(screen.getByText("rightmove")).toBeInTheDocument();
  });

  it("does not render an edit button unless editable and editMode are both true", () => {
    render(<FieldRow listing={makeListing({ address: "1 Test St" })} field="address" label="Address" editable editMode={false} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("FieldRow editing", () => {
  it("saves a numeric field as a Number when the original value was numeric", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(
      <FieldRow
        listing={makeListing({ price_gbp: 500000 })}
        field="price_gbp"
        label="Price"
        currency
        editable
        editMode
        onSave={onSave}
      />
    );

    await user.click(screen.getByRole("button", { name: "✎" }));
    const input = screen.getByRole("textbox");
    await user.clear(input);
    await user.type(input, "550000");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSave).toHaveBeenCalledWith("price_gbp", 550000);
  });

  it("saves an empty value as null", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(
      <FieldRow
        listing={makeListing({ address: "1 Test St" })}
        field="address"
        label="Address"
        editable
        editMode
        onSave={onSave}
      />
    );

    await user.click(screen.getByRole("button", { name: "✎" }));
    await user.clear(screen.getByRole("textbox"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSave).toHaveBeenCalledWith("address", null);
  });

  it("saves a boolean field as an actual boolean, not a string", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(
      <FieldRow
        listing={makeListing({ chain_free: true })}
        field="chain_free"
        label="Chain free"
        boolean
        editable
        editMode
        onSave={onSave}
      />
    );

    await user.click(screen.getByRole("button", { name: "✎" }));
    await user.selectOptions(screen.getByRole("combobox"), "false");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSave).toHaveBeenCalledWith("chain_free", false);
  });

  it("cancel discards the edit without calling onSave", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(
      <FieldRow
        listing={makeListing({ address: "1 Test St" })}
        field="address"
        label="Address"
        editable
        editMode
        onSave={onSave}
      />
    );

    await user.click(screen.getByRole("button", { name: "✎" }));
    await user.clear(screen.getByRole("textbox"));
    await user.type(screen.getByRole("textbox"), "Different address");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("1 Test St")).toBeInTheDocument();
  });
});
