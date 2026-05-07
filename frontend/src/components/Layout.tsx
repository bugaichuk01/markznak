import { Box, FileText, Package, Printer, Settings, ShoppingCart } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

const menuItems = [
  { to: "/settings", label: "Настройки ЧЗ", icon: Settings },
  { to: "/products", label: "Товары и Ozon", icon: Package },
  { to: "/catalog", label: "Национальный каталог", icon: Box },
  { to: "/orders", label: "Заказы СУЗ", icon: ShoppingCart },
  { to: "/upd", label: "Документы УПД", icon: FileText },
  { to: "/labels", label: "Печать этикеток", icon: Printer },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 print:min-h-0 print:bg-white">
      <aside className="fixed inset-y-0 left-0 w-64 border-r border-slate-200 bg-white p-4 shadow-sm print:hidden">
        <div className="mb-6 px-2">
          <p className="text-xs uppercase tracking-wide text-slate-500">MarkZnak Clone</p>
          <p className="text-lg font-semibold">Панель управления</p>
        </div>

        <nav className="space-y-1">
          {menuItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  [
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-blue-50 text-blue-700"
                      : "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
                  ].join(" ")
                }
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>

      <main className="ml-64 p-6 print:ml-0 print:p-0">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm print:rounded-none print:border-0 print:p-0 print:shadow-none">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
