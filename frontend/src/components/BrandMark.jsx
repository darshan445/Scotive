import { Link } from "react-router-dom";

export function BrandMark({ to = "/", size = "md" }) {
    const dot = size === "lg" ? "w-2.5 h-2.5" : "w-2 h-2";
    const text = size === "lg" ? "text-2xl" : "text-lg";
    return (
        <Link to={to} className="inline-flex items-center gap-2 group" data-testid="brand-mark">
            <span className={`${dot} rounded-full bg-foreground transition-transform group-hover:scale-110`} />
            <span className={`font-heading font-black ${text} tracking-tight text-foreground`}>
                Scotive
            </span>
        </Link>
    );
}
