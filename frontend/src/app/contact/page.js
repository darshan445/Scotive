import ContactPage from "@/views/Contact";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Contact Scotive — Demo, Early Access & Support",
    description:
        "Get in touch with Scotive about invoice chasing, a product demo, or early access. Email contact@scotive.com or send a message.",
    path: "/contact",
    keywords: ["contact Scotive", "Scotive support", "invoice chasing demo"],
});

export default function Page() {
    return <ContactPage />;
}
