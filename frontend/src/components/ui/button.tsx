import { Slot } from "radix-ui";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold transition-[background-color,color,border-color,transform,box-shadow] duration-150 active:scale-[.98] disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-brand text-ink hover:bg-brand-strong shadow-[inset_0_-1px_0_rgb(0_0_0/8%)]",
        dark: "bg-ink text-white hover:bg-ink-soft",
        outline: "border border-line-strong bg-surface text-ink hover:bg-subtle",
        ghost: "text-ink-soft hover:bg-subtle",
        link: "h-auto p-0 text-brand-ink underline-offset-4 hover:underline",
      },
      size: { sm: "h-9 px-3.5", md: "h-11 px-5", lg: "h-12 px-6 text-[15px]", icon: "size-10" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export function Button({ className, variant, size, asChild = false, ...props }: ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
