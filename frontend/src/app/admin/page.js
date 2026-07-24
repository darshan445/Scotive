import AdminPage from "@/views/Admin";

export const metadata = {
    title: "Admin",
    robots: { index: false, follow: false },
};

export default function Page() {
    return <AdminPage />;
}
