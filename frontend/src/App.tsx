import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import CardsPage from "./pages/CardsPage";
import LabelsPage from "./pages/LabelsPage";
import OrdersPage from "./pages/OrdersPage";
import ProductsPage from "./pages/ProductsPage";
import SettingsPage from "./pages/SettingsPage";
import UpdPage from "./pages/UpdPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/settings" replace />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/catalog" element={<CardsPage />} />
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/upd" element={<UpdPage />} />
          <Route path="/labels" element={<LabelsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
