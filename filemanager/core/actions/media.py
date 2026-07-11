import os
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QSlider
from PyQt5.QtCore import Qt

from .base import ActionStep
from ...core.media_ops import convert_image

class ConvertImageStep(ActionStep):
    def execute(self, context):
        fmt = self.params.get("format", "PNG")
        try: resize = int(self.params.get("resize", 100))
        except (ValueError, TypeError): resize = 100
        
        for f in context.files:
            if context.should_cancel(): return
            
            if f.extension.lower() not in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff']:
                context.log(f.path, "Convert", "Skipped (Not Image)")
                continue

            if not context.is_dry_run:
                try:
                    result = convert_image(f.path, fmt, resize)
                    new_path = result["output_path"]
                    context.log(f.path, "Convert", f"Converted to {fmt}")
                    
                    # Update context to new file
                    f.path = new_path
                    f.filename = os.path.basename(new_path)
                    f.extension = os.path.splitext(f.filename)[1].lower()
                except Exception as e:
                    context.log(f.path, "Convert", f"Error: {e}")
            else:
                context.log(f.path, "Convert", f"Would convert to {fmt} ({resize}%)")

    def render_ui(self, parent):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Format:"))
        c = QComboBox(parent)
        c.addItems(["PNG", "JPEG", "WEBP", "BMP", "ICO"])
        c.setCurrentText(self.params.get("format", "PNG"))
        c.currentTextChanged.connect(lambda text: self.params.update({"format": text}))
        layout.addWidget(c)
        
        layout.addWidget(QLabel("Resize %:"))
        s = QSlider(Qt.Horizontal, parent)
        s.setRange(10, 200)
        s.setValue(self.params.get("resize", 100))
        s.valueChanged.connect(lambda v: self.params.update({"resize": v}))
        layout.addWidget(s)

    def get_summary(self):
        return f"To {self.params.get('format')} ({self.params.get('resize')}%)"
