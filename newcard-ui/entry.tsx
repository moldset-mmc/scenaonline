import {createRoot} from "react-dom/client";
import Home from "./app/page";
const previewOnly=window.location.protocol==="file:"||(window as Window&{__SCENA_PREVIEW__?:boolean}).__SCENA_PREVIEW__===true;
createRoot(document.getElementById("root")!).render(<Home previewOnly={previewOnly}/>);
