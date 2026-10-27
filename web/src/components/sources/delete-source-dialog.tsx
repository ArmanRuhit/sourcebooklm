"use client";

import { useState } from "react";
import { Trash2Icon } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { deleteSource, getErrorMessage, type Source } from "@/lib/api";

type DeleteSourceDialogProps = {
  source: Source;
  onOpenChange: (open: boolean) => void;
  onDeleted: (id: string) => void;
};

export function DeleteSourceDialog({
  source,
  onOpenChange,
  onDeleted,
}: DeleteSourceDialogProps) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setDeleting(true);
    setError(null);

    try {
      await deleteSource(source.id);
      onDeleted(source.id);
      onOpenChange(false);
    } catch (caught) {
      setError(getErrorMessage(caught));
      setDeleting(false);
    }
  }

  return (
    <AlertDialog open onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogMedia className="bg-destructive/10 text-destructive">
            <Trash2Icon />
          </AlertDialogMedia>
          <AlertDialogTitle>Delete “{source.title}”?</AlertDialogTitle>
          <AlertDialogDescription>
            This removes the source, its stored text, and every indexed chunk.
            This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? "Deleting..." : "Delete source"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
