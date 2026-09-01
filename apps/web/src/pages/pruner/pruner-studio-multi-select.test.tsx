import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PrunerStudioMultiSelect } from "./pruner-studio-multi-select";

describe("PrunerStudioMultiSelect", () => {
  it("explains that a connection is required instead of loading forever", () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <PrunerStudioMultiSelect
          value={[]}
          onChange={vi.fn()}
          disabled
          instanceId={0}
          scope="movies"
        />
      </QueryClientProvider>,
    );

    expect(
      screen.getByTestId("pruner-studio-multiselect-not-configured"),
    ).toHaveTextContent("Connect a server to load studios");
    expect(
      screen.getByText(/Save and test this provider's connection/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Loading studios…")).not.toBeInTheDocument();
  });
});
