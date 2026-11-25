# Steel beam order — total cost memo

You are the engineer for a small steel beam order. All inputs are in this
workdir only.

1. Read `data/order.csv`. It lists the beams ordered: columns `item`, `qty`,
   `unit_price_usd`.
2. Compute the total cost with a Python script (do not do the arithmetic by
   hand). Keep the script in `calc/` and record every computed value in
   `calc/UNITS.md` with value, unit, formula/source, and the script that
   produced it.
3. Write a short memo at `output/memo.md` with:
   - a table of per-item subtotals (item, qty, unit price, subtotal),
   - the grand total in USD with 2 decimals,
   - the path of the script that computed it.
4. Do not invent prices — use only `order.csv`. No placeholders, no TODOs.
