import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import CardsPage from "./pages/CardsPage";
import CodesPage from "./pages/CodesPage";
import ExtraFieldsPage from "./pages/ExtraFieldsPage";
import LabelsPage from "./pages/LabelsPage";
import OrdersPage from "./pages/OrdersPage";
import ProductsPage from "./pages/ProductsPage";
import SettingsPage from "./pages/SettingsPage";
import UpdPage from "./pages/UpdPage";
import UtilisationPage from "./pages/UtilisationPage";
import WithdrawalPage from "./pages/WithdrawalPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/catalog" replace />} />
          <Route path="catalog" element={<CardsPage />} />
          <Route path="orders" element={<OrdersPage />} />
          <Route path="labels" element={<LabelsPage />} />
          <Route path="codes" element={<CodesPage />} />
          <Route path="upd" element={<UpdPage />} />
          <Route path="utilisation" element={<UtilisationPage />} />
          <Route path="withdrawal" element={<WithdrawalPage />} />
          <Route path="extra-fields" element={<ExtraFieldsPage />} />
          <Route path="products" element={<ProductsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
