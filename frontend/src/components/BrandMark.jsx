import { Link } from "react-router-dom";

const SIZES = {
    sm: { img: "h-6 w-6", text: "text-base", gap: "gap-2" },
    md: { img: "h-7 w-7", text: "text-lg", gap: "gap-2.5" },
    lg: { img: "h-8 w-8", text: "text-2xl", gap: "gap-2.5" },
};

export function BrandMark({ to = "/", size = "md", showWordmark = true }) {
    const s = SIZES[size] || SIZES.md;
    return (
        <Link
            to={to}
            className={`inline-flex items-center ${s.gap} group`}
            data-testid="brand-mark"
        >
            <img
                src="/scotive-mark.png"
                alt=""
                width={32}
                height={32}
                className={`${s.img} flex-shrink-0 transition-transform group-hover:scale-105`}
                draggable={false}
            />
            {showWordmark ? (
                <span className={`font-heading font-bold ${s.text} tracking-tight text-foreground`}>
                    Scotive
                </span>
            ) : (
                <span className="sr-only">Scotive</span>
            )}
        </Link>
    );
}
