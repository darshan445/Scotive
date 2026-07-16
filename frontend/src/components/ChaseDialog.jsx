import { ChaseComposer, confirmDiscardComposer } from "@/components/ChaseComposer";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useRef } from "react";

/** Standalone chase modal (e.g. Follow-up prompt on dashboard). */
export function ChaseDialog({ invoice, open, onOpenChange, onSent }) {
    const dirtyRef = useRef(false);

    function requestClose() {
        if (!confirmDiscardComposer(dirtyRef.current)) return;
        onOpenChange(false);
    }

    return (
        <Dialog
            open={open}
            onOpenChange={(next) => {
                if (!next) {
                    if (!confirmDiscardComposer(dirtyRef.current)) return;
                    onOpenChange(false);
                } else {
                    onOpenChange(true);
                }
            }}
        >
            <DialogContent
                className="max-w-2xl"
                data-testid="chase-dialog"
                onEscapeKeyDown={(e) => {
                    if (dirtyRef.current && !window.confirm("Discard this draft?")) {
                        e.preventDefault();
                    }
                }}
                onPointerDownOutside={(e) => {
                    if (dirtyRef.current && !window.confirm("Discard this draft?")) {
                        e.preventDefault();
                    }
                }}
            >
                <DialogHeader className="sr-only">
                    <DialogTitle>
                        {invoice?.status === "disputed" ? "Reply" : "Follow up"}
                    </DialogTitle>
                </DialogHeader>
                {invoice ? (
                    <ChaseComposer
                        invoice={invoice}
                        active={open}
                        initialIntent={invoice._composeIntent || null}
                        onDirtyChange={(d) => { dirtyRef.current = d; }}
                        onCancel={requestClose}
                        onSent={async () => {
                            dirtyRef.current = false;
                            await onSent?.();
                            onOpenChange(false);
                        }}
                    />
                ) : null}
            </DialogContent>
        </Dialog>
    );
}
