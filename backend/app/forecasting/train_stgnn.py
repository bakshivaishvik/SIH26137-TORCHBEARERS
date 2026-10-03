"""
Trains the ST-GNN forecaster (Section 2.1) on synthetic-but-structurally-
realistic traffic data (or, when available, on real SUMO/TraCI-exported
flow data -- see app/simulation/sumo_network.py, which writes to the same
tensor format via `synthetic_traffic.generate_traffic_tensor`-compatible
output). Run directly: `python -m app.forecasting.train_stgnn`.

To swap in real torch_geometric layers instead of the manual adjacency
multiply in stgnn.GraphConvLayer, replace it with
`torch_geometric.nn.GCNConv(in_dim, out_dim)` and pass `edge_index`
instead of `a_hat` -- the rest of the training loop is unchanged.
"""
from __future__ import annotations
import numpy as np
import torch
import torch.nn as nn

from app.forecasting.synthetic_traffic import generate_traffic_tensor, build_supervised_windows
from app.forecasting.stgnn import STGNNForecaster, build_normalized_adjacency


def grid_adjacency(rows: int, cols: int) -> np.ndarray:
    n = rows * cols
    a = np.zeros((n, n))
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            if c + 1 < cols:
                j = i + 1
                a[i, j] = a[j, i] = 1
            if r + 1 < rows:
                j = i + cols
                a[i, j] = a[j, i] = 1
    return a


def train(epochs: int = 15, lookback: int = 12, horizons=(3, 6, 12), rows=6, cols=6):
    n_nodes = rows * cols
    adj = grid_adjacency(rows, cols)
    a_hat = build_normalized_adjacency(adj)

    tensor = generate_traffic_tensor(n_edges=n_nodes, n_timesteps=2000, dt_min=5)
    X, Y = build_supervised_windows(tensor, lookback=lookback, horizons=list(horizons))
    # Y currently (N, n_nodes, n_horizons) but our pooled model predicts a
    # single scalar per horizon (city-wide congestion index) -- average
    # over nodes to match; a per-edge head is the documented extension
    # point in stgnn.py.
    Y_pooled = Y.mean(axis=1)

    split = int(0.85 * len(X))
    X_train, X_val = X[:split], X[split:]
    Y_train, Y_val = Y_pooled[:split], Y_pooled[split:]

    model = STGNNForecaster(n_nodes=n_nodes, lookback=lookback, horizons=list(horizons))
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()

    Xt_train = torch.tensor(X_train, dtype=torch.float32)
    Yt_train = torch.tensor(Y_train, dtype=torch.float32)
    Xt_val = torch.tensor(X_val, dtype=torch.float32)
    Yt_val = torch.tensor(Y_val, dtype=torch.float32)

    batch_size = 32
    history = []
    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(len(Xt_train))
        epoch_loss = 0.0
        for i in range(0, len(perm), batch_size):
            idx = perm[i:i + batch_size]
            xb, yb = Xt_train[idx], Yt_train[idx]
            opt.zero_grad()
            pred = model(xb, a_hat)
            loss = loss_fn(pred, yb)
            loss.backward()
            opt.step()
            epoch_loss += loss.item() * len(idx)
        epoch_loss /= len(Xt_train)

        model.eval()
        with torch.no_grad():
            val_pred = model(Xt_val, a_hat)
            val_loss = loss_fn(val_pred, Yt_val).item()
        history.append({"epoch": epoch, "train_mse": epoch_loss, "val_mse": val_loss})
        print(f"epoch {epoch:02d}  train_mse={epoch_loss:.5f}  val_mse={val_loss:.5f}")

    return model, a_hat, history


if __name__ == "__main__":
    train()
