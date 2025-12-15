"""
FIA Regulations Ingester

Parses and ingests FIA sporting and technical regulations into Qdrant.
Regulations are chunked by article/section for optimal retrieval.

Source: FIA official documents (PDF parsed to text)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RegulationChunk:
    """A chunk of regulation text."""

    content: str
    document_type: str  # "sporting" or "technical"
    year: int
    section: str
    article_number: str
    title: str | None = None


class RegulationsIngester:
    """
    Ingests FIA regulations into the RAG system.

    Regulations are split into chunks by article for better retrieval.
    Each chunk includes metadata for filtering.
    """

    # Common section patterns in FIA regulations
    ARTICLE_PATTERN = re.compile(
        r"(?:Article|ARTICLE)\s+(\d+(?:\.\d+)?)\s*[-–:]?\s*(.+?)(?=\n|$)",
        re.IGNORECASE,
    )

    SECTION_PATTERN = re.compile(
        r"(?:CHAPTER|Chapter|SECTION|Section)\s+(\d+|[A-Z]+)\s*[-–:]?\s*(.+?)(?=\n|$)",
        re.IGNORECASE,
    )

    def __init__(self, rag_service=None):
        """
        Initialize the regulations ingester.

        Args:
            rag_service: RAGService instance (will be created if not provided)
        """
        self.rag_service = rag_service
        self._current_section = "General"

    async def _get_rag_service(self):
        """Get or create RAG service."""
        if self.rag_service is None:
            from agent.rag.service import get_rag_service

            self.rag_service = await get_rag_service()
        return self.rag_service

    def parse_regulations_text(
        self,
        text: str,
        document_type: str,
        year: int,
    ) -> list[RegulationChunk]:
        """
        Parse regulation text into chunks.

        Args:
            text: Raw regulation text
            document_type: "sporting" or "technical"
            year: Regulation year

        Returns:
            List of RegulationChunk objects
        """
        chunks = []
        current_section = "General"
        current_article = ""
        current_title = ""
        current_content = []

        lines = text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for section headers
            section_match = self.SECTION_PATTERN.match(line)
            if section_match:
                # Save previous chunk if exists
                if current_content and current_article:
                    chunks.append(
                        RegulationChunk(
                            content="\n".join(current_content),
                            document_type=document_type,
                            year=year,
                            section=current_section,
                            article_number=current_article,
                            title=current_title,
                        )
                    )
                    current_content = []

                current_section = f"{section_match.group(1)}: {section_match.group(2)}"
                continue

            # Check for article headers
            article_match = self.ARTICLE_PATTERN.match(line)
            if article_match:
                # Save previous chunk if exists
                if current_content and current_article:
                    chunks.append(
                        RegulationChunk(
                            content="\n".join(current_content),
                            document_type=document_type,
                            year=year,
                            section=current_section,
                            article_number=current_article,
                            title=current_title,
                        )
                    )
                    current_content = []

                current_article = article_match.group(1)
                current_title = article_match.group(2).strip()
                current_content = [line]
                continue

            # Regular content line
            if current_article:
                current_content.append(line)

        # Don't forget the last chunk
        if current_content and current_article:
            chunks.append(
                RegulationChunk(
                    content="\n".join(current_content),
                    document_type=document_type,
                    year=year,
                    section=current_section,
                    article_number=current_article,
                    title=current_title,
                )
            )

        logger.info(f"Parsed {len(chunks)} regulation chunks from {document_type} {year}")
        return chunks

    async def ingest_from_text(
        self,
        text: str,
        document_type: str,
        year: int,
    ) -> int:
        """
        Ingest regulations from raw text.

        Args:
            text: Raw regulation text
            document_type: "sporting" or "technical"
            year: Regulation year

        Returns:
            Number of chunks ingested
        """
        rag = await self._get_rag_service()
        chunks = self.parse_regulations_text(text, document_type, year)

        documents = []
        for chunk in chunks:
            documents.append(
                {
                    "content": chunk.content,
                    "metadata": {
                        "document_type": chunk.document_type,
                        "year": chunk.year,
                        "section": chunk.section,
                        "article_number": chunk.article_number,
                        "title": chunk.title or "",
                    },
                }
            )

        if documents:
            count = await rag.add_documents_batch(
                collection="regulations",
                documents=documents,
                batch_size=50,
            )
            logger.info(f"Ingested {count} regulation chunks")
            return count

        return 0

    async def ingest_from_file(
        self,
        file_path: str | Path,
        document_type: str,
        year: int,
    ) -> int:
        """
        Ingest regulations from a text file.

        Args:
            file_path: Path to regulation text file
            document_type: "sporting" or "technical"
            year: Regulation year

        Returns:
            Number of chunks ingested
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {path}")
            return 0

        text = path.read_text(encoding="utf-8")
        return await self.ingest_from_text(text, document_type, year)

    async def ingest_sample_regulations(self) -> int:
        """
        Ingest sample/mock regulations for testing.

        Returns:
            Number of chunks ingested
        """
        # Sample 2024 Sporting Regulations
        sample_sporting = """
CHAPTER 1: GENERAL

Article 1.1 - Regulations
These Formula One Sporting Regulations, together with the Formula One Technical
Regulations and the Formula One Financial Regulations, are adopted by the FIA
pursuant to Article 8.3.2 of the International Sporting Code.

Article 1.2 - General Undertaking
All Competitors, Competitor Personnel, and Drivers participating in the Championship
undertake to observe all the provisions of the International Sporting Code and its
appendices, the Formula One Technical Regulations, the Formula One Financial
Regulations, and these Formula One Sporting Regulations.

CHAPTER 2: LICENCES AND REGISTRATION

Article 2.1 - Competitor Entry
Each Competitor must hold a valid FIA Super Licence. Applications for Super Licences
must be made to the FIA through the applicant's ASN.

Article 2.2 - Driver Eligibility
To be eligible to compete in the Championship, a driver must hold a valid FIA Super
Licence issued by the FIA. The minimum age to hold a Super Licence is 18 years.

CHAPTER 5: SAFETY CAR AND VSC

Article 55.1 - Safety Car Deployment
The Safety Car will be used only if Competitors or officials are in immediate
physical danger on or near the track but the circumstances are not such as to
necessitate suspending the race. It will be driven by an experienced racing driver.

Article 55.2 - Safety Car Procedure
When the order is given to deploy the Safety Car, all marshal posts will display
waved yellow flags and "SC" boards. The Safety Car will join the track with its
orange lights illuminated.

Article 55.3 - Overtaking Behind Safety Car
With the exception of the cases listed below, no driver may overtake another car
on the track while the Safety Car is deployed:
a) If the driver is signaled to do so by the marshals
b) Under the conditions of Article 55.5

Article 55.10 - Safety Car In This Lap
When the Clerk of the Course decides it is safe to call in the Safety Car, the
message "SAFETY CAR IN THIS LAP" will be displayed. At this point, the first car
in line behind the Safety Car may dictate the pace.

CHAPTER 6: SUSPENDING AND RESUMING A RACE

Article 57.1 - Red Flag
Should it become necessary to suspend the race, the Race Director will order red
flags to be shown at all marshal posts and the abort lights to be shown at the
Line. All cars must immediately slow down and proceed to the pit lane.

Article 57.2 - Race Resumption
A rolling start will be used following race suspension. The order at restart will
be determined by the Classification at the time the red flag was shown.
"""

        # Sample 2024 Technical Regulations
        sample_technical = """
CHAPTER 1: DEFINITIONS

Article 1.1 - General
For the purposes of these Technical Regulations, the following definitions apply.

Article 1.2 - Bodywork
The term "bodywork" includes all wholly or partially sprung parts of the car
in contact with the external air stream except cameras and parts associated
with their mountings.

CHAPTER 3: POWER UNIT

Article 3.1 - Power Unit Definition
The power unit consists of:
a) Internal combustion engine (ICE)
b) Motor Generator Unit-Kinetic (MGU-K)
c) Motor Generator Unit-Heat (MGU-H)
d) Energy Store (ES)
e) Turbocharger (TC)
f) Control Electronics (CE)

Article 3.2 - Engine Specifications
The engine must be a four-stroke, spark ignition, 1.6 litre V6 turbo-hybrid.
Maximum engine speed: 15,000 rpm. Maximum fuel flow rate: 100 kg/hour.

Article 3.5 - Cost Cap Components
Power unit manufacturers must supply power units to customer teams at a price
not exceeding the cost cap component price defined in the Financial Regulations.

CHAPTER 4: AERODYNAMICS

Article 4.1 - Aerodynamic Components
All aerodynamic components must comply with the rules laid out in the Technical
Regulations. No moveable aerodynamic devices are permitted.

Article 4.2 - Front Wing
The front wing must be constructed of approved materials and must not exceed
2000mm in width. All front wing elements must be rigidly secured to the car.

Article 4.3 - Rear Wing
The DRS (Drag Reduction System) rear wing flap may be adjusted by the driver
during designated DRS zones. The maximum flap adjustment is 65mm.

CHAPTER 5: TYRES

Article 5.1 - Tyre Supplier
Pirelli is the sole tyre supplier for the 2024 Championship. All teams must
use tyres supplied by Pirelli.

Article 5.2 - Tyre Compounds
The following dry tyre compounds are available:
- C1 (Hardest)
- C2
- C3 (Medium)
- C4
- C5 (Softest)

Three compounds will be nominated for each Event by Pirelli.

Article 5.3 - Tyre Allocation
Each driver is allocated:
- 13 sets of dry weather tyres
- 4 sets of intermediate tyres
- 3 sets of wet weather tyres
"""

        total = 0
        total += await self.ingest_from_text(sample_sporting, "sporting", 2024)
        total += await self.ingest_from_text(sample_technical, "technical", 2024)

        logger.info(f"Ingested {total} sample regulation chunks")
        return total


async def ingest_regulations(
    rag_service=None,
    sample_only: bool = True,
) -> int:
    """
    Convenience function to ingest regulations.

    Args:
        rag_service: Optional RAG service instance
        sample_only: If True, only ingest sample data

    Returns:
        Number of chunks ingested
    """
    ingester = RegulationsIngester(rag_service)

    if sample_only:
        return await ingester.ingest_sample_regulations()

    # TODO: Add real regulation file paths
    return 0
