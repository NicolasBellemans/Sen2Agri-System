#include <limits>

#include "otbWrapperApplication.h"
#include "otbWrapperApplicationFactory.h"

#include "otbVectorImage.h"

#include "ContinuousColorMappingFilter.hxx"

namespace otb
{

namespace Wrapper
{


class ContinuousColorMapping : public Application
{
public:
    typedef ContinuousColorMapping Self;
    typedef Application Superclass;
    typedef itk::SmartPointer<Self> Pointer;
    typedef itk::SmartPointer<const Self> ConstPointer;

    itkNewMacro(Self)

    itkTypeMacro(ContinuousColorMapping, otb::Application)

private:

    void DoInit() ITK_OVERRIDE
    {
        SetName("ContinuousColorMapping");
        SetDescription("Applies a color ramp to an image");

        SetDocName("ContinuousColorMapping");
        SetDocLongDescription(
            "Applies a color ramp to an image");
        SetDocLimitations("None");
        SetDocAuthors("LNI");
        SetDocSeeAlso(" ");

        AddDocTag(Tags::Vector);

        AddParameter(ParameterType_InputImage, "in", "The input image");
        AddParameter(ParameterType_OutputImage, "out", "The output image");
        AddParameter(ParameterType_InputFilename, "map", "The color mapping");

        SetDocExampleParameterValue("in", "in.tif");
        SetDocExampleParameterValue("out", "out.tif");
        SetDocExampleParameterValue("map", "ramp.map");
    }

    void DoUpdateParameters() ITK_OVERRIDE
    {
    }

    void DoExecute() ITK_OVERRIDE
    {
        const auto &file = GetParameterString("map");
        std::ifstream mapFile(file);
        if (!mapFile) {
            itkExceptionMacro("Unable to open " << file);
        }

        auto &&ramp = ReadColorMap(mapFile);

        const auto &in = GetParameterFloatImage("in");
        m_Filter = ContinuousColorMappingFilter::New();
        m_Filter->SetInput(in);

        m_Filter->GetFunctor().SetRamp(std::move(ramp));

        m_Filter->UpdateOutputInformation();

        SetParameterOutputImagePixelType("out", ImagePixelType_uint8);
        SetParameterOutputImage("out", m_Filter->GetOutput());
    }

    static Ramp ReadColorMap(std::istream &mapFile)
    {
        Ramp ramp;

        float min, max;
        uint32_t rMin, gMin, bMin, rMax, gMax, bMax;
        while (mapFile >> min >> max >> rMin >> gMin >> bMin >> rMax >> gMax >> bMax)
        {
            itk::RGBPixel<uint8_t> minColor, maxColor;
            minColor[0] = static_cast<uint8_t>(rMin);
            minColor[1] = static_cast<uint8_t>(gMin);
            minColor[2] = static_cast<uint8_t>(bMin);
            maxColor[0] = static_cast<uint8_t>(rMax);
            maxColor[1] = static_cast<uint8_t>(gMax);
            maxColor[2] = static_cast<uint8_t>(bMax);

            ramp.emplace_back(min, max, minColor, maxColor);
        }

        return ramp;
    }

    ContinuousColorMappingFilter::Pointer m_Filter;
};
}
}

OTB_APPLICATION_EXPORT(otb::Wrapper::ContinuousColorMapping)