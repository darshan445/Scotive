import { Link } from "react-router-dom";

export function BrandMark({ to = "/", size = "md" }) {
    const box = size === "lg" ? "w-8 h-8 text-base" : "w-7 h-7 text-sm";
    const text = size === "lg" ? "text-2xl" : "text-lg";
    return (
        <Link to={to} className="inline-flex items-center gap-2.5 group" data-testid="brand-mark">
            <span
                className={`${box} rounded-lg bg-primary text-primary-foreground font-heading font-bold inline-flex items-center justify-center transition-transform group-hover:scale-105`}
            >
                S
            </span>
            <span className={`font-heading font-bold ${text} tracking-tight text-foreground`}>
                Scotive
            </span>
        </Link>
    );
}
