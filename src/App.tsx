import { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [text, setText] = useState('');
  const [margin, setMargin] = useState(0);
  const width = 3;
  const [dpi, setDpi] = useState(300);
  const [fontSize, setFontSize] = useState(14);
  const [status, setStatus] = useState('');
  const [preview, setPreview] = useState<string | null>(null);
  const [textLength, setTextLength] = useState(0);
  const [printProgress, setPrintProgress] = useState<string>('');
  const [previewProgress, setPreviewProgress] = useState<string>('');
  const [printers, setPrinters] = useState<Array<{ name: string, url: string }>>([]);
  const [selectedPrinter, setSelectedPrinter] = useState<string>('');

  useEffect(() => {
    // Set up event listeners
    const handleProgress = (data: { message: string }) => {
      if (data.message.includes('printer') || data.message.includes('Print')) {
        setPrintProgress(data.message);
      } else {
        setPreviewProgress(data.message);
      }
      setStatus(data.message);
    };

    const handleFinished = (data: { message: string }) => {
      setPrintProgress('');
      setPreviewProgress('');
      setStatus(data.message);
    };

    const handleError = (data: { message: string }) => {
      setPrintProgress('');
      setPreviewProgress('');
      setStatus(data.message);
    };

    const handlePreviewReady = (data: { preview: string, length: string }) => {
      setPreview(data.preview);
      setStatus(`Length: ${data.length}cm`);
      setPreviewProgress('');
    };

    // Add event listeners
    window.pyloid.EventAPI.listen('print_progress', handleProgress);
    window.pyloid.EventAPI.listen('print_finished', handleFinished);
    window.pyloid.EventAPI.listen('print_error', handleError);
    window.pyloid.EventAPI.listen('preview_ready', handlePreviewReady);

    // Cleanup
    return () => {
      window.pyloid.EventAPI.unlisten('print_progress', handleProgress);
      window.pyloid.EventAPI.unlisten('print_finished', handleFinished);
      window.pyloid.EventAPI.unlisten('print_error', handleError);
      window.pyloid.EventAPI.unlisten('preview_ready', handlePreviewReady);
    };
  }, []);

  // Load printers on mount
  useEffect(() => {
    const loadPrinters = async () => {
      const printerList = await window.pyloid.TextPrinterAPI.get_printers();
      setPrinters(printerList);
      if (printerList.length > 0) {
        setSelectedPrinter(printerList[0].url);
        window.pyloid.TextPrinterAPI.set_printer(printerList[0].url);
      }
    };
    loadPrinters();
  }, []);

  // Update selected printer
  const handlePrinterChange = (url: string) => {
    setSelectedPrinter(url);
    window.pyloid.TextPrinterAPI.set_printer(url);
  };

  const handlePreview = async () => {
    try {
      setStatus('Generating preview...');
      await window.pyloid.TextPrinterAPI.preview_text(text, width, dpi, fontSize, margin);
    } catch (error) {
      setStatus('Error: ' + error);
    }
  };

  const handlePrint = async () => {
    try {
      setStatus('Starting print job...');
      const result = await window.pyloid.TextPrinterAPI.print_current();
      setStatus(result);
    } catch (error) {
      setStatus('Error: ' + error);
    }
  };

  return (
    <div className="app">
      <main>
        <div className="editor-panel">
          <div className="settings-bar">
            <div className="setting-group">
              <label>Printer</label>
              <select 
                value={selectedPrinter}
                onChange={(e) => handlePrinterChange(e.target.value)}
                disabled={printers.length === 0}
              >
                {printers.length === 0 && (
                  <option value="">No printers found</option>
                )}
                {printers.map(printer => (
                  <option key={printer.url} value={printer.url}>
                    {printer.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="setting-group">
              <label>Margin (cm)</label>
              <input 
                type="number" 
                value={margin}
                onChange={(e) => setMargin(Number(e.target.value))}
                min={0}
                max={10}
                step={0.5}
              />
            </div>

            <div className="setting-group">
              <label>DPI</label>
              <input 
                type="number" 
                value={dpi}
                onChange={(e) => setDpi(Number(e.target.value))}
                min={72}
                max={600}
                step={1}
              />
            </div>

            <div className="setting-group">
              <label>Font Size (pt)</label>
              <input 
                type="number" 
                value={fontSize}
                onChange={(e) => setFontSize(Number(e.target.value))}
                min={8}
                max={72}
                step={1}
              />
            </div>
          </div>

          <div className="text-editor">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Enter your text here..."
              spellCheck={false}
            />
          </div>

          <div className="actions-bar">
            <button 
              onClick={handlePreview} 
              disabled={!text.trim() || previewProgress !== ''}
            >
              {previewProgress ? 'Generating...' : 'Preview'}
            </button>
            <button 
              onClick={handlePrint} 
              disabled={!text.trim() || !preview || printProgress !== ''}
            >
              {printProgress ? 'Printing...' : 'Print'}
            </button>
            {status && <div className="status">{status}</div>}
          </div>
        </div>

        <div className="preview-panel">
          <div className="preview-scroll">
            {preview ? (
              <img src={preview} alt="Preview" />
            ) : (
              <div className="preview-placeholder">
                Preview will appear here
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
