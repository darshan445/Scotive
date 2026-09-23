import { redirect } from "next/navigation";

export const metadata = {
    title: "Home",
    robots: { index: false, follow: false },
};

export default function Page() {
    redirect("/dashboard");
}
