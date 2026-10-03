import unittest
import numpy as np
import pandas as pd

from app.v2.datasets import scores, splits, train_scaler
from app.v2.forecasting import features, samples, train
from app.v2.imputation import fixed_mask, interpolate, windows


class ModelIsolationTests(unittest.TestCase):
    def test_training_only_scaler_and_windows(self):
        data = np.full((2, 600, 6), 4.0)
        data[:, 420:] = 1000
        data[1] = 8000
        mean, scale = train_scaler(data, 420, [0])
        np.testing.assert_allclose(mean, 4)
        bounds = splits(600, 48)
        self.assertEqual(bounds, [(0,420), (420,510), (510,600)])
        isolated = windows(data, [0], bounds[0], 48)
        self.assertTrue(np.all(isolated == 4))

    def test_masks_only_hide_observed_values_and_reproduce(self):
        data = np.ones((8,48,6))
        data[:,0,:] = np.nan
        for block in [0,6,24]:
            a, b = fixed_mask(data,42,.3,block), fixed_mask(data,42,.3,block)
            np.testing.assert_array_equal(a,b)
            self.assertFalse(a[:,0,:].any())
            hidden = data.copy()
            hidden[a] = np.nan
            restored = interpolate(hidden, np.ones(6))
            self.assertEqual(scores(data[a], restored[a])["MAE"],0)

    def test_forecast_features_never_read_after_cut(self):
        times = pd.date_range("2026-01-01",periods=720,freq="h",tz="UTC")
        data = np.arange(720,dtype=float)[None,:,None].repeat(6,axis=2)
        X, y, _ = samples(data,times,[0],(0,500),0,168,0)
        self.assertEqual(X[0,0],167)
        self.assertEqual(y[0],168)
        self.assertLessEqual(X[:,0].max(), 479)
        self.assertTrue(np.all((y-X[:,0]) == X[:,-1]))

    def test_seasonal_training_reload_and_original_scale(self):
        times = pd.date_range("2026-01-01",periods=1440,freq="h",tz="UTC")
        signal = 20 + 8*np.sin(np.arange(1440)*np.pi/12)
        data = np.tile(signal[None,:,None],(2,1,6))
        artifact, metrics, manifest, passed = train(data,times,["a","b"],"seasonal",42,48,lambda _:None)
        self.assertTrue(passed)
        self.assertTrue(manifest["no_cross_split_windows"])
        self.assertEqual(manifest["holdout_stations"],["b"])
        self.assertLess(metrics["PM2.5"]["test"]["MAE"],1e-10)
        self.assertAlmostEqual(artifact["pollutants"]["PM2.5"]["fill"],20,places=6)


if __name__ == "__main__": unittest.main()
