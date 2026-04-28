import MDEditor from "@uiw/react-md-editor";

interface Props {
  value: string;
  onChange: (v: string) => void;
  preview?: "edit" | "preview" | "live";
  height?: number;
  readOnly?: boolean;
}

export function MarkdownEditor({
  value,
  onChange,
  preview = "edit",
  height = 250,
  readOnly,
}: Props) {
  return (
    <div data-color-mode="light" className="dark:hidden">
      <MDEditor
        value={value}
        onChange={(v) => !readOnly && onChange(v ?? "")}
        preview={preview}
        height={height}
        previewOptions={{ skipHtml: false }}
      />
    </div>
  );
}
