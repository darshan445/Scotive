import ContactPage from "@/views/Contact";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Contact",
    description:
        "You already invoiced them. Scotive watches the thread and the open invoice, and handles the next chase. Email contact@scotive.com.",
    path: "/contact",
});

export default function Page() {
    return <ContactPage />;
}
